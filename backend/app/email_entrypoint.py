"""Explicit, opt-in launcher for SupportFlow AI email service.

Default command is configuration check only.
No database or SMTP connection occurs during --check.
"""

import argparse
import asyncio
import signal

from .config import settings
from .email_service import run_service
from .email_transport import validate_email_address


def configuration_errors():
    """Return safe error labels without disclosing credentials."""

    errors = []

    mode = getattr(settings, "email_delivery_mode", "")
    if mode not in {"test", "production"}:
        errors.append("Invalid email delivery mode")
    elif mode == "test":
        from .email_transport import configured_test_recipients
        recipients = configured_test_recipients()
        if not recipients:
            errors.append("Test recipient allowlist is empty")

    if not settings.email_delivery_enabled:
        errors.append("Email delivery is disabled")

    if not settings.email_smtp_starttls:
        errors.append("SMTP STARTTLS is required")

    if not settings.email_smtp_host.strip():
        errors.append("SMTP host is missing")

    if not 1 <= settings.email_smtp_port <= 65535:
        errors.append("Invalid SMTP port")

    if not settings.email_smtp_username.strip():
        errors.append("SMTP username is missing")

    if not settings.email_smtp_password:
        errors.append("SMTP password is missing")

    try:
        validate_email_address(settings.email_from_address)
    except ValueError:
        errors.append("Sender email is invalid")

    if not 1 <= settings.email_worker_batch_size <= 100:
        errors.append("Invalid worker batch size")

    if not 1 <= settings.email_worker_poll_seconds <= 3600:
        errors.append("Invalid worker polling interval")

    if settings.email_max_attempts < 1:
        errors.append("Invalid maximum retry attempts")

    if settings.email_smtp_timeout_seconds < 1:
        errors.append("Invalid SMTP timeout")

    return errors


async def _run_with_signals():
    """Run service until a shutdown signal is received."""

    stop_event = asyncio.Event()
    old_handlers = {}

    def request_shutdown(signum, frame):
        stop_event.set()

    try:
        for name in ("SIGINT", "SIGTERM"):
            signum = getattr(signal, name, None)

            if signum is not None:
                old_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_shutdown)

        return await run_service(stop_event)
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


async def _run_disabled_idle():
    """Keep the Compose-managed worker alive without DB/SMTP activity."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, name, None)
        if signum is not None:
            try:
                loop.add_signal_handler(signum, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
    print("Email delivery disabled; worker idle (no database/SMTP calls)", flush=True)
    await stop_event.wait()
    print("Email worker stopped: disabled idle shutdown", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SupportFlow AI email worker"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--check",
        action="store_true",
        help="Check configuration without starting the worker",
    )

    group.add_argument(
        "--run",
        action="store_true",
        help="Explicitly run email delivery worker",
    )

    args = parser.parse_args(argv)

    errors = configuration_errors()

    if args.run and not settings.email_delivery_enabled:
        try:
            asyncio.run(_run_disabled_idle())
        except KeyboardInterrupt:
            pass
        return 0

    if not args.run:
        print("EMAIL WORKER CONFIGURATION CHECK")
        print(
            "Delivery status: "
            + (
                "ENABLED"
                if settings.email_delivery_enabled
                else "DISABLED"
            )
        )

        if errors:
            print("Readiness: NOT READY")

            for error in errors:
                print(" - " + error)
        else:
            print("Readiness: CONFIGURATION READY")

        print("Database connections: 0")
        print("SMTP calls: 0")
        print("Worker started: NO")
        return 0

    if errors:
        print("WORKER START REFUSED: invalid configuration")

        for error in errors:
            print(" - " + error)

        return 2

    print("Email worker starting with explicit --run")

    try:
        summary = asyncio.run(_run_with_signals())
    except Exception as exc:
        # Avoid logging exception details, which can include
        # connection strings or SMTP credentials.
        print(
            "Worker failed: "
            + type(exc).__name__
        )
        return 1

    print("Worker stopped: " + summary.stopped_reason)
    print("Cycles: " + str(summary.cycles))
    print("Processed: " + str(summary.processed))
    print("Sent: " + str(summary.sent))
    print("Retry: " + str(summary.retry))
    print("Failed: " + str(summary.failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
