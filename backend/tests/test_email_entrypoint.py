"""No-network safety tests for the email CLI launcher."""

from app import email_entrypoint


def test_default_mode_does_not_start_worker(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        email_entrypoint.settings,
        "email_delivery_enabled",
        False,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Worker must not start")

    monkeypatch.setattr(
        email_entrypoint,
        "_run_with_signals",
        forbidden,
    )

    assert email_entrypoint.main([]) == 0

    output = capsys.readouterr().out

    assert "Worker started: NO" in output


def test_check_mode_reports_disabled(monkeypatch, capsys):
    monkeypatch.setattr(
        email_entrypoint.settings,
        "email_delivery_enabled",
        False,
    )

    result = email_entrypoint.main(["--check"])
    output = capsys.readouterr().out

    assert result == 0
    assert "DISABLED" in output
    assert "NOT READY" in output


def test_run_enters_disabled_idle_mode(monkeypatch):
    monkeypatch.setattr(
        email_entrypoint.settings,
        "email_delivery_enabled",
        False,
    )

    async def idle():
        return None

    monkeypatch.setattr(
        email_entrypoint,
        "_run_disabled_idle",
        idle,
    )

    assert email_entrypoint.main(["--run"]) == 0


def test_configuration_never_exposes_password(
    monkeypatch,
    capsys,
):
    secret = "DO_NOT_PRINT_THIS_SECRET"

    monkeypatch.setattr(
        email_entrypoint.settings,
        "email_delivery_enabled",
        False,
    )
    monkeypatch.setattr(
        email_entrypoint.settings,
        "email_smtp_password",
        secret,
    )

    email_entrypoint.main(["--check"])

    output = capsys.readouterr().out

    assert secret not in output
