"""Regression tests for customer email verification gates."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, params
from fastapi.routing import APIRoute

from app.main import (
    app,
    get_current_customer,
    require_verified_customer,
)


def customer(verified):
    return SimpleNamespace(
        id=123,
        email_verified_at=(
            datetime.now(timezone.utc) if verified else None
        ),
    )


def test_unverified_customer_is_denied():
    with pytest.raises(HTTPException) as error:
        require_verified_customer(customer(False))

    assert error.value.status_code == 403
    assert error.value.detail == "Email verification required"


def test_verified_customer_is_allowed():
    verified = customer(True)

    assert require_verified_customer(verified) is verified


protected_routes = [
    ("POST", "/chat"),
    ("GET", "/customer/tickets"),
    ("GET", "/customer/tickets/{ticket_id}/messages"),
    ("GET", "/notifications/customer"),
    ("POST", "/notifications/customer/{notification_id}/read"),
]


def route_dependencies(method, path):
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    ]

    assert len(routes) == 1
    return [
        dependency.call
        for dependency in routes[0].dependant.dependencies
    ]


@pytest.mark.parametrize("method,path", protected_routes)
def test_customer_routes_require_verified_email(method, path):
    dependencies = route_dependencies(method, path)

    assert require_verified_customer in dependencies
    assert get_current_customer not in dependencies


def test_resend_route_remains_authentication_only():
    dependencies = route_dependencies(
        "POST",
        "/auth/resend-verification",
    )

    assert get_current_customer in dependencies
    assert require_verified_customer not in dependencies


def test_verification_gate_depends_on_authentication():
    dependencies = [
        dependency.dependency
        for dependency in require_verified_customer.__defaults__
        if isinstance(dependency, params.Depends)
    ]

    assert dependencies == [get_current_customer]
