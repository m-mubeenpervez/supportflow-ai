"""Database-backed authorization for admin JWT sessions."""

from fastapi import Depends, HTTPException, Security
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from .admin_auth import decode_admin_access_token
from .db import Session
from .models import AdminUser


admin_bearer = HTTPBearer(auto_error=False)

ALLOWED_ADMIN_ROLES = frozenset({
    "admin",
    "super_admin",
})


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Security(
        admin_bearer
    ),
) -> AdminUser:
    """Validate token, account state, role and session version."""

    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired admin session",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    identity = decode_admin_access_token(
        credentials.credentials
    )

    if identity is None:
        raise unauthorized

    admin_id, token_version = identity

    async with Session() as db:
        account = await db.get(AdminUser, admin_id)

        if (
            account is None
            or account.is_active is not True
            or not account.password_hash
            or account.role not in ALLOWED_ADMIN_ROLES
            or type(account.session_version) is not int
            or account.session_version != token_version
        ):
            raise unauthorized

        return account


def require_super_admin(
    account: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """Permit super-admin-only operations."""

    if account.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Insufficient admin permissions",
        )

    return account
