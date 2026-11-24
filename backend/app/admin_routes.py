"""Separate administrator authentication endpoints."""

from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update

from .admin_auth import create_admin_access_token
from .admin_login_throttle import admin_login_throttle
from .admin_dependencies import (ALLOWED_ADMIN_ROLES, get_current_admin)
from .auth import hash_password, verify_password
from .auth_schemas import TokenResponse
from .db import Session
from .models import AdminUser


router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@lru_cache(maxsize=1)
def _dummy_admin_password_hash() -> str:
    """Provide a valid dummy hash for unknown accounts."""
    return hash_password(
        "supportflow-nonexistent-admin-password-placeholder"
    )


@router.post("/login", response_model=TokenResponse)
async def admin_login(data: AdminLoginRequest, request: Request):
    """Authenticate an active administrator."""

    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    email = str(data.email).strip().lower()

    # Use the directly connected client address.
    # Do not trust user-controlled forwarded headers.
    client_key = (
        request.client.host
        if request.client is not None
        else "unknown-client"
    )

    if not admin_login_throttle.begin_attempt(client_key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": "300"},
        )

    success = False
    try:
        async with Session() as db:
            account = await db.scalar(
                select(AdminUser).where(AdminUser.email == email)
            )

            stored_hash = (
                account.password_hash
                if account is not None and account.password_hash
                else _dummy_admin_password_hash()
            )

            password_valid = verify_password(
                data.password,
                stored_hash,
            )

            if account is None or not password_valid:
                raise unauthorized

            if (
                account.is_active is not True
                or account.role not in ALLOWED_ADMIN_ROLES
                or type(account.session_version) is not int
                or account.session_version < 0
            ):
                raise unauthorized

            token = create_admin_access_token(
                account.id,
                account.session_version,
            )


            success = True
            return TokenResponse(
                access_token=token,
                token_type="bearer",
            )
    finally:
        admin_login_throttle.finish_attempt(
            client_key, success=success
        )


@router.get("/me")
async def admin_me(
    account: AdminUser = Depends(get_current_admin),
):
    """Return the authenticated admin's safe profile."""

    return {
        "id": account.id,
        "email": account.email,
        "role": account.role,
        "is_active": account.is_active,
    }


@router.post("/logout")
async def admin_logout(
    account: AdminUser = Depends(get_current_admin),
):
    """Revoke all existing admin tokens for this account."""

    async with Session() as db:
        statement = (
            update(AdminUser)
            .where(
                AdminUser.id == account.id,
                AdminUser.is_active.is_(True),
                AdminUser.session_version == account.session_version,
            )
            .values(
                session_version=AdminUser.session_version + 1
            )
            .returning(AdminUser.id)
        )

        result = await db.execute(statement)
        updated_id = result.scalar_one_or_none()

        if updated_id is None:
            await db.rollback()
            raise HTTPException(
                status_code=401,
                detail="Admin session no longer valid",
            )

        await db.commit()

    return {"message": "Logged out successfully"}
