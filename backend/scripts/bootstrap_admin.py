"""Create the first Super Admin for a fresh installation.

This command is intentionally local/operational only.  It refuses the
recovered and automated-test databases, never accepts a password argument,
and serializes concurrent attempts with a PostgreSQL advisory lock.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

from app.admin_provisioning import AdminProvisioningError, prepare_admin_credentials
from app.config import settings
from app.db import Session, init_db
from app.models import AdminUser


PROTECTED_DATABASES = {"supportflow_recovery", "supportflow_test_db"}
LOCK_KEY = 781236451


def database_name() -> str:
    return make_url(settings.database_url).database or ""


def ensure_bootstrap_target_is_safe() -> str:
    name = database_name()
    configured = (settings.application_database_name or "").strip().lower()
    if name.lower() in PROTECTED_DATABASES or configured in PROTECTED_DATABASES:
        raise RuntimeError(
            "Refusing bootstrap on a protected database; configure a fresh installation database"
        )
    if not name:
        raise RuntimeError("DATABASE_URL must include a database name")
    return name


async def create_initial_super_admin(email: str, password: str) -> str:
    """Create exactly one initial Super Admin inside an atomic transaction."""
    normalized, password_hash = prepare_admin_credentials(email, password)
    async with Session.begin() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        existing = await session.scalar(
            select(func.count(AdminUser.id)).where(AdminUser.role == "super_admin")
        )
        if existing:
            raise RuntimeError("An initial Super Admin already exists")
        session.add(
            AdminUser(
                email=normalized,
                password_hash=password_hash,
                role="super_admin",
                is_active=True,
                session_version=0,
            )
        )
    return normalized


async def run(email: str) -> str:
    ensure_bootstrap_target_is_safe()
    # Safe for a brand-new database; this does not perform destructive migrations.
    await init_db()
    return await create_initial_super_admin(email, await asyncio.to_thread(get_password))


def get_password() -> str:
    password = getpass.getpass("Super Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise AdminProvisioningError("Passwords do not match")
    return password


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create the first SupportFlow Super Admin")
    parser.add_argument("--email", required=True, help="Initial administrator email address")
    args = parser.parse_args(argv)
    try:
        normalized = asyncio.run(run(args.email))
    except (AdminProvisioningError, RuntimeError, IntegrityError) as exc:
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 1
    print(f"Initial Super Admin created: {normalized}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
