from datetime import timedelta
from uuid import uuid4

import pytest

from portfolio.contexts.identity.domain.admin import AdminUser, LockoutPolicy
from portfolio.contexts.identity.domain.credentials import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Email,
    check_password_strength,
)
from portfolio.contexts.identity.domain.errors import (
    AccountLockedError,
    InvalidEmailError,
    WeakPasswordError,
)
from portfolio.contexts.identity.domain.session import AdminSession, hash_token
from tests.unit.identity.fakes import START


class TestEmail:
    def test_normalizes_case_and_whitespace(self) -> None:
        assert Email.parse("  Erick@Example.DEV ").value == "erick@example.dev"

    def test_str_is_the_address(self) -> None:
        assert str(Email.parse("a@b.co")) == "a@b.co"

    @pytest.mark.parametrize("raw", ["", "no-at.dev", "a@b", "a b@c.dev", "a@@b.dev"])
    def test_rejects_malformed(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            Email.parse(raw)

    def test_rejects_too_long(self) -> None:
        with pytest.raises(InvalidEmailError):
            Email.parse("a" * 250 + "@b.dev")


class TestPasswordStrength:
    def test_accepts_long_enough(self) -> None:
        check_password_strength("x" * MIN_PASSWORD_LENGTH)

    @pytest.mark.parametrize(
        "password",
        ["x" * (MIN_PASSWORD_LENGTH - 1), "x" * (MAX_PASSWORD_LENGTH + 1), " leading-space-pw"],
    )
    def test_rejects(self, password: str) -> None:
        with pytest.raises(WeakPasswordError):
            check_password_strength(password)


class TestLockoutPolicy:
    @pytest.mark.parametrize(
        ("attempts", "expected"),
        [
            (1, None),
            (4, None),
            (5, timedelta(minutes=1)),
            (6, timedelta(minutes=2)),
            (7, timedelta(minutes=4)),
            (11, timedelta(hours=1)),  # 64 min, capped
            (10_000, timedelta(hours=1)),
        ],
    )
    def test_progressive_and_capped(self, attempts: int, expected: timedelta | None) -> None:
        assert LockoutPolicy().lock_duration(attempts) == expected


def _admin(**overrides: object) -> AdminUser:
    fields: dict[str, object] = {
        "id": uuid4(),
        "email": Email.parse("erick@example.dev"),
        "password_hash": "h",
        "created_at": START,
    }
    fields.update(overrides)
    return AdminUser(**fields)  # type: ignore[arg-type]


class TestAdminUser:
    def test_not_locked_by_default(self) -> None:
        assert not _admin().is_locked(START)

    def test_lock_expires(self) -> None:
        admin = _admin(locked_until=START + timedelta(minutes=1))
        assert admin.is_locked(START)
        assert not admin.is_locked(START + timedelta(minutes=1))

    def test_failures_lock_after_free_attempts(self) -> None:
        policy = LockoutPolicy()
        admin = _admin()
        for _ in range(policy.free_attempts):
            admin = admin.with_failed_attempt(START, policy)
        assert admin.failed_attempts == policy.free_attempts
        assert admin.locked_until is None
        admin = admin.with_failed_attempt(START, policy)
        assert admin.locked_until == START + policy.base_lock

    def test_success_resets_and_updates_hash(self) -> None:
        admin = _admin(failed_attempts=7, locked_until=START).with_successful_login("new")
        assert (admin.failed_attempts, admin.locked_until, admin.password_hash) == (0, None, "new")


class TestSession:
    def test_hash_token_is_stable_sha256(self) -> None:
        assert hash_token("abc") == hash_token("abc")
        assert len(hash_token("abc")) == 64
        assert hash_token("abc") != "abc"

    def test_expiry_is_inclusive(self) -> None:
        session = AdminSession(uuid4(), uuid4(), "h", START, START + timedelta(hours=1))
        assert not session.is_expired(START)
        assert session.is_expired(START + timedelta(hours=1))


def test_locked_error_carries_the_deadline() -> None:
    error = AccountLockedError(START)
    assert error.until == START
    assert START.isoformat() in str(error)
