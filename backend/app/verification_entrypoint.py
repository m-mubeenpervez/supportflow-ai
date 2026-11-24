"""Explicit opt-in verification email delivery CLI (one job maximum).

--check: configuration only; no database, no SMTP.
--once --send-real-email: claim and process at most one pending job.
Run separately from the support-notification email worker.
"""
import argparse
import asyncio
import signal

from .email_entrypoint import configuration_errors
from .config import settings
from .verification_runtime_config import get_verification_email_config


async def _run_service(runtime):
    """Poll the verification outbox until a shutdown signal is received."""
    from .verification_delivery_processor import process_one_verification_email

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, name, None)
        if signum is not None:
            try:
                loop.add_signal_handler(signum, stop.set)
            except (NotImplementedError, RuntimeError):
                pass

    while not stop.is_set():
        result = await process_one_verification_email(
            encryption_key=runtime.encryption_key,
            verification_base_url=runtime.base_url,
        )
        if result not in {
            "sent", "empty", "ineligible", "retry", "failed",
            "ownership_lost", "disabled",
        }:
            raise RuntimeError("Unexpected verification worker result")
        if result == "disabled":
            return 0
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.email_worker_poll_seconds
            )
        except asyncio.TimeoutError:
            pass
    return 0


async def _run_disabled_idle():
    """Keep the Compose-managed worker alive without DB/SMTP activity."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, name, None)
        if signum is not None:
            try:
                loop.add_signal_handler(signum, stop.set)
            except (NotImplementedError, RuntimeError):
                pass
    print("Email delivery disabled; verification worker idle (no database/SMTP calls)", flush=True)
    await stop.wait()
    print("Verification worker stopped: disabled idle shutdown", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SupportFlow verification email")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--send-real-email", action="store_true")
    args = parser.parse_args(argv)
    if args.check and (args.once or args.run or args.send_real_email):
        parser.error("--check must be used alone")
    if args.once and args.run:
        parser.error("--once and --run are mutually exclusive")
    if args.send_real_email and not (args.once or args.run):
        parser.error("--send-real-email requires --once or --run")

    errors = configuration_errors()
    if args.run and not settings.email_delivery_enabled:
        try:
            return asyncio.run(_run_disabled_idle())
        except KeyboardInterrupt:
            return 0
    try:
        runtime = get_verification_email_config()
    except RuntimeError:
        errors.append("Verification encryption key or URL is invalid")
        runtime = None

    if not args.once and not args.run:
        print("VERIFICATION WORKER CHECK (no database / SMTP calls)")
        print("READY" if not errors else "NOT READY")
        for label in errors:
            print(" -", label)
        return 0 if not errors else 2

    if not args.send_real_email:
        print("REFUSED: delivery requires --send-real-email")
        return 2
    if errors or runtime is None:
        print("REFUSED: configuration incomplete")
        for label in errors:
            print(" -", label)
        return 2

    if args.run:
        try:
            return asyncio.run(_run_service(runtime))
        except Exception as exc:
            print("Verification worker failed:", type(exc).__name__)
            return 1

    # Import here so --check does not import the DB worker.
    from .verification_delivery_processor import process_one_verification_email

    try:
        result = asyncio.run(process_one_verification_email(
            encryption_key=runtime.encryption_key,
            verification_base_url=runtime.base_url,
        ))
    except Exception as exc:
        # Never print SMTP details or raw token.
        print("Verification worker failed:", type(exc).__name__)
        return 1
    print("Verification job status:", result)
    return 0 if result in {"sent", "empty", "ineligible"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
