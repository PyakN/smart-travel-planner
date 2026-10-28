"""Accounts: sign-up, log-in sessions and a limit on failed log-ins.

- Passwords are hashed with argon2id (argon2-cffi's defaults), in a worker thread: a hash
  takes tens of milliseconds of CPU. A log-in with an unknown email verifies a dummy hash,
  so it takes as long as a wrong password.
- A session is a random token in an HttpOnly cookie; the database keeps only its SHA-256
  (`UserSession.token_hash`) and an expiry.
- Failed log-ins are limited per email, in memory (`LoginLimiter`).
"""

import asyncio
import hashlib
import math
import secrets
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserSession

MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_S = 15 * 60

_hasher = PasswordHasher()


class EmailTakenError(Exception):
    pass


class WrongCredentialsError(Exception):
    pass


class TooManyLoginsError(Exception):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"locked for {retry_after_s} s")
        self.retry_after_s = retry_after_s


class LoginLimiter:
    """At most `max_failures` failed log-ins per email within `window_s`.

    Every attempt counts as a failure until its password checks out, so guesses sent at
    once cannot slip past the limit while their hashes are verified. Kept in memory: per
    process and forgotten on restart; the oldest emails are forgotten beyond `max_keys`.
    """

    def __init__(
        self,
        max_failures: int = MAX_FAILED_LOGINS,
        window_s: float = FAILED_LOGIN_WINDOW_S,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self.clock = clock
        self.max_keys = max_keys
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()

    def attempt(self, key: str) -> None:
        """Count a log-in attempt; TooManyLoginsError if `key` has to wait."""
        now = self.clock()
        failures = self._failures.pop(key, deque())
        while failures and failures[0] <= now - self.window_s:
            failures.popleft()
        self._failures[key] = failures  # most recently used last
        if len(failures) >= self.max_failures:
            raise TooManyLoginsError(max(1, math.ceil(failures[0] + self.window_s - now)))
        failures.append(now)
        while len(self._failures) > self.max_keys:
            self._failures.popitem(last=False)

    def succeeded(self, key: str) -> None:
        """The password was right: forget the failures."""
        self._failures.pop(key, None)


@dataclass(frozen=True)
class Login:
    user: User
    token: str  # for the cookie; only its hash is stored
    expires_at: datetime


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def password_matches(password_hash: str, password: str) -> bool:
    try:
        return await asyncio.to_thread(_hasher.verify, password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


async def start_session(session: AsyncSession, user: User, days: int) -> Login:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=days)
    session.add(UserSession(user_id=user.id, token_hash=token_hash(token), expires_at=expires_at))
    await session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.expires_at <= func.now()
        )
    )
    await session.commit()
    return Login(user, token, expires_at)


async def sign_up(
    session: AsyncSession, *, email: str, password: str, display_name: str, days: int
) -> Login:
    """A new account, logged in. `email` must be normalized (lowercase)."""
    user = User(email=email, password_hash=await hash_password(password), display_name=display_name)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # the only unique column is the email
        await session.rollback()
        raise EmailTakenError(email) from exc
    return await start_session(session, user, days)


async def log_in(
    session: AsyncSession, limiter: LoginLimiter, *, email: str, password: str, days: int
) -> Login:
    limiter.attempt(email)
    user = await session.scalar(select(User).where(User.email == email))
    matches = await password_matches(user.password_hash if user else _dummy_hash(), password)
    if user is None or not matches:
        raise WrongCredentialsError(email)
    limiter.succeeded(email)
    if _hasher.check_needs_rehash(user.password_hash):  # argon2-cffi raised its defaults
        user.password_hash = await hash_password(password)
    return await start_session(session, user, days)


async def session_user(session: AsyncSession, token: str) -> User | None:
    """The user a session token belongs to, unless it expired or was logged out."""
    user: User | None = await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == token_hash(token), UserSession.expires_at > func.now())
    )
    return user


async def log_out(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
    await session.commit()


async def delete_account(session: AsyncSession, user: User) -> None:
    """The user, their sessions and everything they saved go; plans stay (share links)."""
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
