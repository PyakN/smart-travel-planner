"""Accounts: sign up, log in and out, read or delete the current user.

The session lives in an HttpOnly, SameSite=Lax cookie with `Path=/`: the browser reaches
the API through the frontend's same-origin `/api` proxy, so the paths it sees differ from
the API's own.
"""

import math

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import (
    SESSION_COOKIE,
    CurrentUserDep,
    LoginLimiterDep,
    SessionDep,
    SessionTokenDep,
    SettingsDep,
)
from app.config import Settings
from app.db.models import User
from app.schemas.account import LoginRequest, SignupRequest, UserOut
from app.services import accounts
from app.services.accounts import (
    EmailTakenError,
    Login,
    TooManyLoginsError,
    WrongCredentialsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _start(response: Response, login: Login, settings: Settings) -> UserOut:
    response.set_cookie(
        SESSION_COOKIE,
        login.token,
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return user_out(login.user)


def _end(response: Response, settings: Settings) -> None:
    # With the attributes it was set with, or browsers keep it.
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name, created_at=user.created_at
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def sign_up(
    body: SignupRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    """Create an account and log in."""
    try:
        login = await accounts.sign_up(
            session,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            days=settings.session_days,
        )
    except EmailTakenError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists. Log in instead."
        ) from exc
    return _start(response, login, settings)


@router.post("/login")
async def log_in(
    body: LoginRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    limiter: LoginLimiterDep,
) -> UserOut:
    """Log in; too many failed log-ins for an email lock it for a while (429)."""
    try:
        login = await accounts.log_in(
            session, limiter, email=body.email, password=body.password, days=settings.session_days
        )
    except TooManyLoginsError as exc:
        minutes = math.ceil(exc.retry_after_s / 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed log-ins. Try again in {minutes} min.",
            headers={"Retry-After": str(exc.retry_after_s)},
        ) from exc
    except WrongCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.") from exc
    return _start(response, login, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(
    response: Response, session: SessionDep, settings: SettingsDep, token: SessionTokenDep = None
) -> None:
    if token:
        await accounts.log_out(session, token)
    _end(response, settings)


@router.get("/me")
async def read_me(user: CurrentUserDep) -> UserOut:
    return user_out(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    user: CurrentUserDep, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    """Delete the account, its sessions and its saved trips. Plans stay: share links work."""
    await accounts.delete_account(session, user)
    _end(response, settings)
