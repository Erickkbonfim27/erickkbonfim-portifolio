from argon2 import PasswordHasher as Argon2

from portfolio.contexts.identity.infrastructure.security import (
    Argon2PasswordHasher,
    SystemClock,
    UrlSafeTokenGenerator,
)

# Cheap parameters: these tests check behaviour, not hardness.
FAST = Argon2(time_cost=1, memory_cost=8, parallelism=1)


def test_argon2_round_trip() -> None:
    hasher = Argon2PasswordHasher(FAST)
    password_hash = hasher.hash("correct horse battery staple")
    assert password_hash.startswith("$argon2id$")
    assert hasher.verify(password_hash, "correct horse battery staple")
    assert not hasher.verify(password_hash, "wrong")


def test_argon2_rejects_garbage_hash() -> None:
    assert not Argon2PasswordHasher(FAST).verify("not-a-hash", "whatever")


def test_argon2_flags_hashes_made_with_weaker_parameters() -> None:
    weak_hash = Argon2PasswordHasher(FAST).hash("pw")
    assert Argon2PasswordHasher().needs_rehash(weak_hash)
    assert not Argon2PasswordHasher(FAST).needs_rehash(weak_hash)


def test_default_hasher_uses_library_defaults() -> None:
    assert Argon2PasswordHasher().hash("pw").startswith("$argon2id$")


def test_tokens_are_long_and_unique() -> None:
    tokens = {UrlSafeTokenGenerator().new_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(token) >= 43 for token in tokens)


def test_clock_is_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None
