from datetime import timedelta

import pytest

from portfolio.contexts.identity.domain.errors import (
    AccountLockedError,
    AdminAlreadyExistsError,
    InvalidCredentialsError,
    InvalidEmailError,
    SessionInvalidError,
    WeakPasswordError,
)
from portfolio.contexts.identity.domain.session import hash_token
from tests.unit.identity.fakes import DUMMY_HASH, SESSION_TTL, START, Harness, make_harness

EMAIL = "erick@example.dev"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def h() -> Harness:
    return make_harness()


async def _with_admin(h: Harness) -> None:
    await h.use_cases.create_admin(EMAIL, PASSWORD)


class TestCreateAdmin:
    async def test_creates_with_hashed_password(self, h: Harness) -> None:
        admin = await h.use_cases.create_admin(" Erick@Example.dev ", PASSWORD)
        assert admin.email.value == EMAIL
        assert admin.password_hash == f"hashed:{PASSWORD}"
        assert admin.created_at == START
        assert h.store.admins == {admin.id: admin}

    async def test_rejects_duplicate_email(self, h: Harness) -> None:
        await _with_admin(h)
        with pytest.raises(AdminAlreadyExistsError):
            await h.use_cases.create_admin(EMAIL.upper(), PASSWORD)
        assert len(h.store.admins) == 1

    async def test_rejects_invalid_email(self, h: Harness) -> None:
        with pytest.raises(InvalidEmailError):
            await h.use_cases.create_admin("nope", PASSWORD)

    async def test_rejects_weak_password(self, h: Harness) -> None:
        with pytest.raises(WeakPasswordError):
            await h.use_cases.create_admin(EMAIL, "short")


class TestLogin:
    async def test_creates_a_session_storing_only_the_token_hash(self, h: Harness) -> None:
        await _with_admin(h)
        result = await h.use_cases.login(EMAIL, PASSWORD)
        assert result.token == "token-1"
        assert result.expires_at == START + SESSION_TTL
        [session] = h.store.sessions.values()
        assert session.token_hash == hash_token("token-1")

    async def test_unknown_email_still_verifies_a_hash(self, h: Harness) -> None:
        with pytest.raises(InvalidCredentialsError):
            await h.use_cases.login("ghost@example.dev", PASSWORD)
        assert h.hasher.verified == [DUMMY_HASH]

    async def test_malformed_email_is_just_invalid_credentials(self, h: Harness) -> None:
        with pytest.raises(InvalidCredentialsError):
            await h.use_cases.login("not an email", PASSWORD)
        assert h.hasher.verified == [DUMMY_HASH]

    async def test_wrong_password_counts_a_failure(self, h: Harness) -> None:
        await _with_admin(h)
        with pytest.raises(InvalidCredentialsError):
            await h.use_cases.login(EMAIL, "wrong password!!")
        [admin] = h.store.admins.values()
        assert admin.failed_attempts == 1
        assert h.store.sessions == {}

    async def test_locks_after_repeated_failures_even_for_the_right_password(
        self, h: Harness
    ) -> None:
        await _with_admin(h)
        for _ in range(5):
            with pytest.raises(InvalidCredentialsError):
                await h.use_cases.login(EMAIL, "wrong password!!")
        with pytest.raises(AccountLockedError) as locked:
            await h.use_cases.login(EMAIL, PASSWORD)
        assert locked.value.until == START + timedelta(minutes=1)

    async def test_login_works_again_after_the_lock_and_resets_the_count(self, h: Harness) -> None:
        await _with_admin(h)
        for _ in range(5):
            with pytest.raises(InvalidCredentialsError):
                await h.use_cases.login(EMAIL, "wrong password!!")
        h.clock.advance(timedelta(minutes=1))
        await h.use_cases.login(EMAIL, PASSWORD)
        [admin] = h.store.admins.values()
        assert (admin.failed_attempts, admin.locked_until) == (0, None)

    async def test_upgrades_an_outdated_hash(self, h: Harness) -> None:
        await _with_admin(h)
        [admin] = h.store.admins.values()
        h.store.admins[admin.id] = admin.with_successful_login("legacy-hash")
        h.hasher.accept_any = True
        h.hasher.outdated.add("legacy-hash")
        await h.use_cases.login(EMAIL, PASSWORD)
        assert h.store.admins[admin.id].password_hash == f"hashed:{PASSWORD}"


class TestLogout:
    async def test_deletes_the_session(self, h: Harness) -> None:
        await _with_admin(h)
        result = await h.use_cases.login(EMAIL, PASSWORD)
        await h.use_cases.logout(result.token)
        assert h.store.sessions == {}

    async def test_unknown_token_is_a_no_op(self, h: Harness) -> None:
        commits = h.store.commits
        await h.use_cases.logout("never-issued")
        assert h.store.commits == commits


class TestAuthenticate:
    async def test_returns_the_admin(self, h: Harness) -> None:
        await _with_admin(h)
        result = await h.use_cases.login(EMAIL, PASSWORD)
        admin = await h.use_cases.authenticate(result.token)
        assert admin.email.value == EMAIL

    async def test_unknown_token(self, h: Harness) -> None:
        with pytest.raises(SessionInvalidError):
            await h.use_cases.authenticate("never-issued")

    async def test_expired_session_is_rejected_and_removed(self, h: Harness) -> None:
        await _with_admin(h)
        result = await h.use_cases.login(EMAIL, PASSWORD)
        h.clock.advance(SESSION_TTL)
        with pytest.raises(SessionInvalidError):
            await h.use_cases.authenticate(result.token)
        assert h.store.sessions == {}

    async def test_session_of_a_deleted_admin(self, h: Harness) -> None:
        await _with_admin(h)
        result = await h.use_cases.login(EMAIL, PASSWORD)
        h.store.admins.clear()
        with pytest.raises(SessionInvalidError):
            await h.use_cases.authenticate(result.token)
