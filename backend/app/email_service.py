"""Controlled lifecycle for the email outbox worker.

Importing this module never starts background processing.
A separate service launcher will be added after verification.
"""

import asyncio
from dataclasses import dataclass

from .config import settings
from .email_runner import run_batch


@dataclass(frozen=True)
class ServiceSummary:
    cycles: int
    processed: int
    sent: int
    retry: int
    failed: int
    ownership_lost: int
    stopped_reason: str


async def run_service(
    stop_event: asyncio.Event,
    *,
    batch_runner=None,
    poll_seconds=None,
    max_cycles=None,
) -> ServiceSummary:
    """Run email batches until stopped or disabled.

    Shutdown is cooperative: an active batch finishes first.
    Unexpected batch errors propagate to the caller.
    """

    if not isinstance(stop_event, asyncio.Event):
        raise TypeError("stop_event must be an asyncio.Event")

    interval = (
        settings.email_worker_poll_seconds
        if poll_seconds is None
        else poll_seconds
    )

    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not 1 <= interval <= 3600
    ):
        raise ValueError("Invalid worker polling interval")

    if max_cycles is not None and (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or not 1 <= max_cycles <= 10000
    ):
        raise ValueError("Invalid maximum cycle count")

    runner = batch_runner if batch_runner is not None else run_batch

    totals = {
        "processed": 0,
        "sent": 0,
        "retry": 0,
        "failed": 0,
        "ownership_lost": 0,
    }

    cycles = 0
    reason = "stopped"

    while not stop_event.is_set():
        if not settings.email_delivery_enabled:
            reason = "disabled"
            break

        summary = await runner()
        cycles += 1

        for name in totals:
            totals[name] += getattr(summary, name)

        if summary.disabled or not settings.email_delivery_enabled:
            reason = "disabled"
            break

        if max_cycles is not None and cycles >= max_cycles:
            reason = "cycle_limit"
            break

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=interval,
            )
        except asyncio.TimeoutError:
            pass

    return ServiceSummary(
        cycles=cycles,
        stopped_reason=reason,
        **totals,
    )
