"""Tests for isolated admin login throttling."""

from app.admin_login_throttle import (
    AdminLoginThrottle,
    MAX_FAILURES,
    WINDOW_SECONDS,
)


def test_first_attempt_allowed():
    throttle = AdminLoginThrottle()
    assert throttle.allowed("client-a")


def test_blocks_after_five_failures():
    throttle = AdminLoginThrottle()

    for _ in range(MAX_FAILURES):
        assert throttle.allowed("client-a")
        throttle.record_failure("client-a")

    assert not throttle.allowed("client-a")


def test_different_clients_are_independent():
    throttle = AdminLoginThrottle()

    for _ in range(MAX_FAILURES):
        throttle.record_failure("client-a")

    assert not throttle.allowed("client-a")
    assert throttle.allowed("client-b")


def test_limit_expires_after_window():
    current = [1000.0]
    throttle = AdminLoginThrottle(clock=lambda: current[0])

    for _ in range(MAX_FAILURES):
        throttle.record_failure("client-a")

    assert not throttle.allowed("client-a")

    current[0] += WINDOW_SECONDS + 1

    assert throttle.allowed("client-a")


def test_clear_resets_failed_attempts():
    throttle = AdminLoginThrottle()

    for _ in range(MAX_FAILURES):
        throttle.record_failure("client-a")

    assert not throttle.allowed("client-a")

    throttle.clear("client-a")

    assert throttle.allowed("client-a")

def test_new_client_denied_at_capacity(monkeypatch):
    import app.admin_login_throttle as module

    monkeypatch.setattr(module, "MAX_TRACKED_CLIENTS", 2)

    throttle = AdminLoginThrottle()

    throttle.record_failure("client-a")
    throttle.record_failure("client-b")

    assert throttle.allowed("client-a")
    assert not throttle.allowed("client-c")

    throttle.record_failure("client-c")

    assert len(throttle.failures) == 2
    assert "client-c" not in throttle.failures


def test_expired_clients_release_capacity(monkeypatch):
    import app.admin_login_throttle as module

    monkeypatch.setattr(module, "MAX_TRACKED_CLIENTS", 2)

    current = [1000.0]
    throttle = AdminLoginThrottle(clock=lambda: current[0])

    throttle.record_failure("client-a")
    throttle.record_failure("client-b")

    assert not throttle.allowed("client-c")

    current[0] += WINDOW_SECONDS + 1

    assert throttle.allowed("client-c")

    throttle.record_failure("client-c")

    assert "client-c" in throttle.failures
    assert len(throttle.failures) == 1


def test_existing_client_remains_tracked_at_capacity(monkeypatch):
    import app.admin_login_throttle as module

    monkeypatch.setattr(module, "MAX_TRACKED_CLIENTS", 1)

    throttle = AdminLoginThrottle()

    for _ in range(MAX_FAILURES):
        throttle.record_failure("client-a")

    assert not throttle.allowed("client-a")
    assert not throttle.allowed("client-b")
    assert len(throttle.failures) == 1

def test_atomic_reservation_prevents_overlapping_admissions():
    throttle = AdminLoginThrottle()
    key = "198.51.100.50"

    admissions = [
        throttle.begin_attempt(key)
        for _ in range(MAX_FAILURES + 5)
    ]

    assert sum(admissions) == MAX_FAILURES
    assert throttle.inflight[key] == MAX_FAILURES

    for accepted in admissions:
        if accepted:
            throttle.finish_attempt(key, success=False)

    assert not throttle.begin_attempt(key)
    assert key not in throttle.inflight


def test_success_releases_reservation():
    throttle = AdminLoginThrottle()
    key = "client-success"

    assert throttle.begin_attempt(key)
    throttle.finish_attempt(key, success=True)

    assert key not in throttle.inflight
    assert key not in throttle.failures


def test_failed_attempt_releases_and_records():
    throttle = AdminLoginThrottle()
    key = "client-failure"

    assert throttle.begin_attempt(key)
    throttle.finish_attempt(key, success=False)

    assert key not in throttle.inflight
    assert len(throttle.failures[key]) == 1


def test_active_reservations_count_against_capacity(monkeypatch):
    import app.admin_login_throttle as module

    monkeypatch.setattr(module, "MAX_TRACKED_CLIENTS", 1)

    throttle = AdminLoginThrottle()

    assert throttle.begin_attempt("client-a")
    assert not throttle.begin_attempt("client-b")

    throttle.finish_attempt("client-a", success=True)

    assert throttle.begin_attempt("client-b")
    throttle.finish_attempt("client-b", success=True)


def test_duplicate_completion_rejected():
    import pytest

    throttle = AdminLoginThrottle()
    assert throttle.begin_attempt("client-a")

    throttle.finish_attempt("client-a", success=True)

    with pytest.raises(RuntimeError):
        throttle.finish_attempt("client-a", success=False)


def test_failed_attempt_expires_after_window():
    current = [1000.0]
    throttle = AdminLoginThrottle(clock=lambda: current[0])

    for _ in range(MAX_FAILURES):
        assert throttle.begin_attempt("client-a")
        throttle.finish_attempt("client-a", success=False)

    assert not throttle.begin_attempt("client-a")

    current[0] += WINDOW_SECONDS + 1

    assert throttle.begin_attempt("client-a")
    throttle.finish_attempt("client-a", success=True)
