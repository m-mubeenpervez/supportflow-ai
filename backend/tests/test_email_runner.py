"""Tests for bounded email batch execution."""

import pytest

from app import email_runner


def enable_email(monkeypatch, enabled=True):
    monkeypatch.setattr(
        email_runner.settings,
        "email_delivery_enabled",
        enabled,
    )


@pytest.mark.asyncio
async def test_disabled_batch_never_calls_processor(monkeypatch):
    enable_email(monkeypatch, False)

    async def forbidden(**kwargs):
        raise AssertionError("Processor must not run")

    summary = await email_runner.run_batch(
        processor=forbidden,
    )

    assert summary.disabled is True
    assert summary.processed == 0


@pytest.mark.asyncio
async def test_empty_queue_stops_immediately(monkeypatch):
    enable_email(monkeypatch)

    calls = []

    async def fake_processor(**kwargs):
        calls.append(1)
        return "empty"

    summary = await email_runner.run_batch(
        processor=fake_processor,
    )

    assert len(calls) == 1
    assert summary.processed == 0


@pytest.mark.asyncio
async def test_batch_limit_is_respected(monkeypatch):
    enable_email(monkeypatch)

    calls = []

    async def fake_processor(**kwargs):
        calls.append(1)
        return "sent"

    summary = await email_runner.run_batch(
        processor=fake_processor,
        batch_size=3,
    )

    assert len(calls) == 3
    assert summary.processed == 3
    assert summary.sent == 3


@pytest.mark.asyncio
async def test_aggregate_results(monkeypatch):
    enable_email(monkeypatch)

    results = iter([
        "sent",
        "retry",
        "failed",
        "ownership_lost",
        "empty",
    ])

    async def fake_processor(**kwargs):
        return next(results)

    summary = await email_runner.run_batch(
        processor=fake_processor,
        batch_size=10,
    )

    assert summary.processed == 4
    assert summary.sent == 1
    assert summary.retry == 1
    assert summary.failed == 1
    assert summary.ownership_lost == 1
    assert summary.disabled is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_limit",
    [0, -1, 101, True, 1.5, "10"],
)
async def test_invalid_batch_size(monkeypatch, invalid_limit):
    enable_email(monkeypatch)

    with pytest.raises(ValueError):
        await email_runner.run_batch(
            batch_size=invalid_limit,
        )


@pytest.mark.asyncio
async def test_unexpected_result_is_rejected(monkeypatch):
    enable_email(monkeypatch)

    async def fake_processor(**kwargs):
        return "unexpected"

    with pytest.raises(
        RuntimeError,
        match="Unexpected email worker result",
    ):
        await email_runner.run_batch(
            processor=fake_processor,
        )


@pytest.mark.asyncio
async def test_processor_exception_propagates(monkeypatch):
    enable_email(monkeypatch)

    async def fake_processor(**kwargs):
        raise RuntimeError("Simulated database error")

    with pytest.raises(
        RuntimeError,
        match="Simulated database error",
    ):
        await email_runner.run_batch(
            processor=fake_processor,
        )
