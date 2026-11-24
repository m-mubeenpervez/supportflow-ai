"""Mock-only tests for worker service lifecycle."""

import asyncio
from types import SimpleNamespace

import pytest

from app import email_service


def batch_result(
    *,
    processed=0,
    sent=0,
    retry=0,
    failed=0,
    ownership_lost=0,
    disabled=False,
):
    return SimpleNamespace(
        processed=processed,
        sent=sent,
        retry=retry,
        failed=failed,
        ownership_lost=ownership_lost,
        disabled=disabled,
    )


def enable(monkeypatch, value=True):
    monkeypatch.setattr(
        email_service.settings,
        "email_delivery_enabled",
        value,
    )


@pytest.mark.asyncio
async def test_disabled_service_never_runs_batch(monkeypatch):
    enable(monkeypatch, False)

    async def forbidden():
        raise AssertionError("Batch must not execute")

    result = await email_service.run_service(
        asyncio.Event(),
        batch_runner=forbidden,
        max_cycles=1,
    )

    assert result.cycles == 0
    assert result.stopped_reason == "disabled"


@pytest.mark.asyncio
async def test_service_obeys_cycle_limit(monkeypatch):
    enable(monkeypatch)

    calls = []

    async def fake_batch():
        calls.append(1)
        return batch_result(processed=1, sent=1)

    result = await email_service.run_service(
        asyncio.Event(),
        batch_runner=fake_batch,
        poll_seconds=1,
        max_cycles=2,
    )

    assert len(calls) == 2
    assert result.cycles == 2
    assert result.processed == 2
    assert result.sent == 2
    assert result.stopped_reason == "cycle_limit"


@pytest.mark.asyncio
async def test_shutdown_finishes_active_batch(monkeypatch):
    enable(monkeypatch)

    stop = asyncio.Event()

    async def fake_batch():
        await asyncio.sleep(0)
        stop.set()
        return batch_result(
            processed=1,
            retry=1,
        )

    result = await email_service.run_service(
        stop,
        batch_runner=fake_batch,
        poll_seconds=1,
    )

    assert result.cycles == 1
    assert result.retry == 1
    assert result.stopped_reason == "stopped"


@pytest.mark.asyncio
async def test_pre_requested_shutdown_skips_processing(monkeypatch):
    enable(monkeypatch)

    stop = asyncio.Event()
    stop.set()

    async def forbidden():
        raise AssertionError("Batch must not execute")

    result = await email_service.run_service(
        stop,
        batch_runner=forbidden,
    )

    assert result.cycles == 0
    assert result.stopped_reason == "stopped"


@pytest.mark.asyncio
async def test_batch_error_propagates(monkeypatch):
    enable(monkeypatch)

    async def broken_batch():
        raise RuntimeError("Simulated database outage")

    with pytest.raises(RuntimeError, match="database outage"):
        await email_service.run_service(
            asyncio.Event(),
            batch_runner=broken_batch,
            max_cycles=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [0, -1, 3601, True])
async def test_invalid_polling_interval(monkeypatch, interval):
    enable(monkeypatch)

    with pytest.raises(ValueError):
        await email_service.run_service(
            asyncio.Event(),
            poll_seconds=interval,
        )


@pytest.mark.asyncio
async def test_service_stops_when_delivery_disabled(monkeypatch):
    enable(monkeypatch)

    async def disable_after_batch():
        enable(monkeypatch, False)
        return batch_result(processed=1, sent=1)

    result = await email_service.run_service(
        asyncio.Event(),
        batch_runner=disable_after_batch,
        max_cycles=2,
    )

    assert result.cycles == 1
    assert result.sent == 1
    assert result.stopped_reason == "disabled"
