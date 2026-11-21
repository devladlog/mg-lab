from __future__ import annotations

from pathlib import Path

import pytest

from contoso_azure import cli

ROOT = Path(__file__).resolve().parent.parent


def test_emulator_flag_does_not_swallow_the_subcommand() -> None:
    args = cli._parser().parse_args(["--emulator", "list"])
    assert args.emulator is True
    assert args.command == "list"


def test_bad_container_name_exits_2_before_any_network_call(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--emulator", "--input-container", "Bad_Name", "list"]) == 2
    assert "not a valid container name" in capsys.readouterr().err


def test_missing_account_url_exits_2(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTOSO_STORAGE_ACCOUNT_URL", raising=False)
    assert cli.main(["list"]) == 2
    assert "CONTOSO_STORAGE_ACCOUNT_URL" in capsys.readouterr().err


@pytest.mark.integration
def test_seed_process_list_end_to_end(
    emulator_url: str, capsys: pytest.CaptureFixture[str], requests_csv: bytes
) -> None:
    base = [
        "--emulator",
        "--emulator-url",
        emulator_url,
        "--input-container",
        "cli-in",
        "--output-container",
        "cli-out",
    ]
    assert cli.main([*base, "seed", str(ROOT / "samples" / "requests.csv")]) == 0
    assert cli.main([*base, "process", "--approvers", str(ROOT / "samples" / "approvers.json")]) == 0
    assert "8 written" in capsys.readouterr().out
    assert cli.main([*base, "process", "--approvers", str(ROOT / "samples" / "approvers.json")]) == 0
    assert "8 already existed" in capsys.readouterr().out
    assert cli.main([*base, "list"]) == 0
    assert capsys.readouterr().out.count("cli-out/") == 8
