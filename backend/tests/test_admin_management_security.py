"""Unit-level RBAC input checks. Full HTTP integration requires PostgreSQL."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from types import SimpleNamespace
from app.admin_dependencies import require_super_admin
from app.admin_management import CreateAdmin, AccountAction, parse_dates


def test_normal_admin_cannot_access_super_admin_capabilities():
    with pytest.raises(HTTPException) as exc:
        require_super_admin(SimpleNamespace(role='admin'))
    assert exc.value.status_code == 403


def test_super_admin_can_access_management():
    admin = SimpleNamespace(role='super_admin')
    assert require_super_admin(admin) is admin


def test_malformed_date_range_rejected():
    with pytest.raises(HTTPException) as exc:
        parse_dates('2026-11-21', '2026-11-20')
    assert exc.value.status_code == 422


def test_short_admin_password_not_accepted():
    with pytest.raises(ValidationError):
        CreateAdmin(email='normal@example.com',password='short')


def test_empty_action_reason_not_accepted():
    with pytest.raises(ValidationError):
        AccountAction(reason='x')


def test_http_normal_admin_cannot_list_or_create_staff():
    """HTTP authorization regression: hiding a UI button is not security."""
    import asyncio
    from fastapi import FastAPI
    from app.admin_management import router
    from app.admin_dependencies import get_current_admin
    import httpx

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(role='admin', id=99, email='normal@example.invalid')
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            get_result = await client.get('/admin/management/admins')
            post_result = await client.post('/admin/management/admins', json={'email':'staff@example.invalid','password':'some-long-password-here'})
            return get_result.status_code, post_result.status_code
    try:
        assert asyncio.run(check()) == (403,403)
    finally:
        app.dependency_overrides.pop(get_current_admin,None)
