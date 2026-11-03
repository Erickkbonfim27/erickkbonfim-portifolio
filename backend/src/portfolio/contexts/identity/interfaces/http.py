import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from portfolio.contexts.identity.application.use_cases import IdentityUseCases
from portfolio.contexts.identity.domain.admin import AdminUser
from portfolio.contexts.identity.domain.credentials import MAX_PASSWORD_LENGTH
from portfolio.contexts.identity.domain.errors import (
    AccountLockedError,
    InvalidCredentialsError,
    SessionInvalidError,
)


@dataclass(frozen=True, slots=True)
class AuthCookie:
    name: str
    secure: bool
    domain: str | None


def _use_cases(request: Request) -> IdentityUseCases:
    return cast(IdentityUseCases, request.app.state.identity)


def _cookie(request: Request) -> AuthCookie:
    return cast(AuthCookie, request.app.state.auth_cookie)


UseCases = Annotated[IdentityUseCases, Depends(_use_cases)]
Cookie = Annotated[AuthCookie, Depends(_cookie)]


async def current_admin(request: Request, use_cases: UseCases, cookie: Cookie) -> AdminUser:
    """Dependency for every admin route. 401 unless the request carries a live session."""
    token = request.cookies.get(cookie.name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        return await use_cases.authenticate(token)
    except SessionInvalidError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated") from None


CurrentAdmin = Annotated[AdminUser, Depends(current_admin)]

# Kept out of the public OpenAPI schema. That hides nothing from an attacker;
# it just keeps the public docs about the public API.
router = APIRouter(prefix="/admin/auth", include_in_schema=False)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class AdminOut(BaseModel):
    email: str


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(body: LoginBody, response: Response, use_cases: UseCases, cookie: Cookie) -> None:
    try:
        result = await use_cases.login(body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from None
    except AccountLockedError as locked:
        wait = math.ceil((locked.until - datetime.now(UTC)).total_seconds())
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many failed attempts",
            headers={"Retry-After": str(max(wait, 1))},
        ) from None
    response.set_cookie(
        cookie.name,
        result.token,
        # Max-Age wins over Expires and is relative, so a browser with a wrong clock
        # keeps the session for its real lifetime.
        max_age=result.lifetime_seconds,
        expires=result.expires_at,
        path="/",
        domain=cookie.domain,
        secure=cookie.secure,
        httponly=True,
        samesite="strict",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, use_cases: UseCases, cookie: Cookie) -> None:
    token = request.cookies.get(cookie.name)
    if token:
        await use_cases.logout(token)
    response.delete_cookie(
        cookie.name,
        path="/",
        domain=cookie.domain,
        secure=cookie.secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/me")
async def me(admin: CurrentAdmin) -> AdminOut:
    return AdminOut(email=admin.email.value)
