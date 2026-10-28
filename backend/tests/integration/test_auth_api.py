"""Accounts end to end: sign-up, log-in, sessions in a cookie, the failed log-in limit."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.deps import get_login_limiter
from app.db.models import User, UserSession
from app.services.accounts import LoginLimiter, token_hash
from tests.integration.conftest import (
    PASSWORD,
    SessionFactory,
    session_token,
    sign_up,
    use_session,
)
from tests.test_accounts import Clock


def log_in(client: TestClient, email: str, password: str = PASSWORD) -> int:
    return client.post("/auth/login", json={"email": email, "password": password}).status_code


@pytest.fixture
def clock(visitor: TestClient) -> Iterator[Clock]:
    """A fresh failed log-in limit (3 a minute) on a clock the test moves."""
    clock = Clock()
    limiter = LoginLimiter(max_failures=3, window_s=60, clock=clock)
    overrides = visitor.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_login_limiter] = lambda: limiter
    yield clock
    overrides.pop(get_login_limiter)


def test_sign_up_logs_in(visitor: TestClient, db_session: SessionFactory) -> None:
    response = visitor.post(
        "/auth/signup",
        json={"email": " Ana.Silva@Example.COM", "password": PASSWORD, "display_name": " Ana "},
    )
    assert response.status_code == 201, response.text
    user = response.json()
    assert (user["email"], user["display_name"]) == ("ana.silva@example.com", "Ana")

    [cookie] = response.headers.get_list("set-cookie")
    assert cookie.startswith("session=")
    for attribute in ["HttpOnly", "Path=/", "SameSite=lax", f"Max-Age={30 * 24 * 3600}"]:
        assert attribute in cookie
    assert "Secure" not in cookie  # SESSION_COOKIE_SECURE is off by default
    assert visitor.get("/auth/me").json() == user

    async def stored() -> tuple[str, list[str]]:
        async with db_session() as session:
            account = await session.scalar(select(User).where(User.id == user["id"]))
            assert account is not None
            hashes = await session.scalars(
                select(UserSession.token_hash).where(UserSession.user_id == user["id"])
            )
            return account.password_hash, list(hashes)

    password_hash, hashes = asyncio.run(stored())
    assert password_hash.startswith("$argon2id$") and PASSWORD not in password_hash
    assert hashes == [token_hash(session_token(visitor))]


def test_an_email_has_one_account(visitor: TestClient) -> None:
    user = sign_up(visitor)
    response = visitor.post(
        "/auth/signup",
        json={"email": user["email"].upper(), "password": "another one", "display_name": "Bo"},
    )
    assert response.status_code == 409
    assert response.json()["detail"].startswith("An account with this email already exists")


@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "ana@example"), ("password", "short"), ("display_name", "  ")],
)
def test_sign_up_checks_the_form(visitor: TestClient, field: str, value: str) -> None:
    body = {"email": "new@example.com", "password": PASSWORD, "display_name": "Ana", field: value}
    assert visitor.post("/auth/signup", json=body).status_code == 422


def test_log_in_and_out(visitor: TestClient) -> None:
    user = sign_up(visitor)
    first = session_token(visitor)
    visitor.cookies.clear()
    assert visitor.get("/auth/me").status_code == 401

    assert log_in(visitor, user["email"].title()) == 200  # emails ignore case
    assert visitor.get("/auth/me").json() == user
    second = session_token(visitor)
    assert second != first

    response = visitor.post("/auth/logout")
    assert response.status_code == 204
    [cookie] = response.headers.get_list("set-cookie")
    assert cookie.startswith('session=""') and "Max-Age=0" in cookie and "Path=/" in cookie
    use_session(visitor, second)
    assert visitor.get("/auth/me").status_code == 401  # the session is gone, not just the cookie
    use_session(visitor, first)
    assert visitor.get("/auth/me").json() == user  # other log-ins stay


def test_wrong_credentials_get_one_answer(visitor: TestClient) -> None:
    user = sign_up(visitor)
    visitor.cookies.clear()
    wrong_password = visitor.post(
        "/auth/login", json={"email": user["email"], "password": "wrong password"}
    )
    unknown_email = visitor.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json() == {"detail": "Wrong email or password."}
        assert "set-cookie" not in response.headers


def test_failed_log_ins_are_limited(visitor: TestClient, clock: Clock) -> None:
    user = sign_up(visitor)
    other = sign_up(visitor, "Bo")
    visitor.cookies.clear()
    for _ in range(3):
        assert log_in(visitor, user["email"], "wrong password") == 401
        clock.now += 5

    locked = visitor.post("/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert locked.status_code == 429  # even with the right password
    assert locked.headers["Retry-After"] == "45"
    assert locked.json()["detail"] == "Too many failed log-ins. Try again in 1 min."
    assert log_in(visitor, other["email"]) == 200  # other accounts are not affected

    clock.now += 45
    assert log_in(visitor, user["email"]) == 200
    assert log_in(visitor, user["email"], "wrong password") == 401  # the count starts over


def test_sessions_expire(visitor: TestClient, db_session: SessionFactory) -> None:
    sign_up(visitor)
    digest = token_hash(session_token(visitor))

    async def expire() -> None:
        async with db_session() as session, session.begin():
            await session.execute(
                update(UserSession)
                .where(UserSession.token_hash == digest)
                .values(expires_at=UserSession.created_at)
            )

    asyncio.run(expire())
    assert visitor.get("/auth/me").status_code == 401


def test_delete_account(visitor: TestClient, db_session: SessionFactory) -> None:
    user = sign_up(visitor)
    token = session_token(visitor)
    response = visitor.delete("/auth/me")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    use_session(visitor, token)
    assert visitor.get("/auth/me").status_code == 401
    assert log_in(visitor, user["email"]) == 401

    async def remaining() -> int:
        async with db_session() as session:
            rows = await session.scalars(
                select(UserSession.id).where(UserSession.user_id == user["id"])
            )
            return len(list(rows))

    assert asyncio.run(remaining()) == 0


def test_no_cookie_no_user(visitor: TestClient) -> None:
    response = visitor.get("/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Log in first."}
    visitor.cookies.set("session", "made-up")
    assert visitor.get("/auth/me").status_code == 401
    assert visitor.delete("/auth/me").status_code == 401
    assert visitor.post("/auth/logout").status_code == 204  # logging out is always fine
