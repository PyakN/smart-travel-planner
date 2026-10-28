import asyncio

import pytest
from pydantic import ValidationError

from app.schemas.account import LoginRequest, SignupRequest
from app.services.accounts import (
    LoginLimiter,
    TooManyLoginsError,
    hash_password,
    password_matches,
    token_hash,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_locks_an_email_after_too_many_attempts() -> None:
    clock = Clock()
    limiter = LoginLimiter(max_failures=3, window_s=60, clock=clock)
    for _ in range(3):
        limiter.attempt("ana@example.com")
        clock.now += 10
    with pytest.raises(TooManyLoginsError) as locked:
        limiter.attempt("ana@example.com")
    assert locked.value.retry_after_s == 30  # until the first attempt is a minute old
    limiter.attempt("bob@example.com")  # other emails are not affected

    clock.now += 30
    limiter.attempt("ana@example.com")  # one attempt aged out: one more try
    with pytest.raises(TooManyLoginsError):
        limiter.attempt("ana@example.com")


def test_a_right_password_clears_the_failures() -> None:
    limiter = LoginLimiter(max_failures=2, window_s=60, clock=Clock())
    limiter.attempt("ana@example.com")
    limiter.attempt("ana@example.com")
    limiter.succeeded("ana@example.com")
    limiter.attempt("ana@example.com")
    limiter.attempt("ana@example.com")


def test_limiter_forgets_the_oldest_emails_beyond_its_size() -> None:
    limiter = LoginLimiter(max_failures=1, window_s=60, clock=Clock(), max_keys=2)
    limiter.attempt("a@example.com")
    limiter.attempt("b@example.com")
    with pytest.raises(TooManyLoginsError):
        limiter.attempt("a@example.com")  # a is the most recent now
    limiter.attempt("c@example.com")  # b is forgotten
    limiter.attempt("b@example.com")
    with pytest.raises(TooManyLoginsError):
        limiter.attempt("c@example.com")


def test_passwords_are_hashed_with_argon2id() -> None:
    async def check() -> None:
        stored = await hash_password("correct horse")
        assert stored.startswith("$argon2id$")
        assert await password_matches(stored, "correct horse")
        assert not await password_matches(stored, "Correct horse")
        assert not await password_matches("not a hash", "correct horse")

    asyncio.run(check())


def test_tokens_are_stored_as_sha256() -> None:
    assert token_hash("abc") == token_hash("abc")
    assert len(token_hash("abc")) == 64
    assert token_hash("abc") != token_hash("abd")


def test_emails_are_normalized() -> None:
    login = LoginRequest(email="  Ana.Silva@Example.COM ", password="x")
    assert login.email == "ana.silva@example.com"
    for bad in ["ana", "ana@example", "an a@example.com", ""]:
        with pytest.raises(ValidationError):
            LoginRequest(email=bad, password="x")


def test_sign_up_rules() -> None:
    signup = SignupRequest(email="a@b.pt", password="12345678", display_name="  Ana ")
    assert signup.display_name == "Ana"
    with pytest.raises(ValidationError):
        SignupRequest(email="a@b.pt", password="1234567", display_name="Ana")
    with pytest.raises(ValidationError):
        SignupRequest(email="a@b.pt", password="12345678", display_name="   ")
