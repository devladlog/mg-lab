import pytest

from costwatch import __main__ as cli
from costwatch.waste import CHECKS, find_waste, to_markdown


def test_findings_are_priced_and_the_empty_disk_costs_nothing(prices, fake_az):
    report = find_waste(prices, az=fake_az.path)
    by_name = {f.resource_id.rsplit("/", 1)[-1]: f for f in report.findings}
    assert set(by_name) == {"disk-orphaned-os", "disk-empty-never-used", "pip-contoso-forgotten", "plan-contoso-leftover"}
    assert by_name["disk-orphaned-os"].monthly == pytest.approx(1.38, abs=0.01)        # S4 LRS
    assert by_name["disk-empty-never-used"].monthly == 0.0                              # Learn: no storage yet
    assert "never attached" in by_name["disk-empty-never-used"].note
    assert by_name["pip-contoso-forgotten"].monthly == pytest.approx(0.0045 * 730, abs=0.02)
    assert by_name["plan-contoso-leftover"].monthly == pytest.approx(11.80, abs=0.01)
    assert report.monthly_total == pytest.approx(1.38 + 3.28 + 11.80, abs=0.03)


def test_every_check_runs_its_query_file_with_paging_size(prices, fake_az):
    find_waste(prices, az=fake_az.path)
    calls = fake_az.calls()
    assert len(calls) == len(CHECKS)
    for args in calls:
        assert args[:2] == ["graph", "query"] and args[args.index("--first") + 1] == "1000"
        assert args[args.index("--output") + 1] == "json"


def test_skip_token_pages_are_concatenated(prices, fake_az, monkeypatch):
    monkeypatch.setenv("FAKE_AZ_PAGED", "1")
    report = find_waste(prices, az=fake_az.path)
    assert sum(1 for f in report.findings if "disks" in f.resource_id) == 2
    disk_calls = [c for c in fake_az.calls() if "microsoft.compute/disks" in c[c.index("-q") + 1]]
    assert len(disk_calls) == 2 and "--skip-token" in disk_calls[1]


def test_markdown_report(prices, fake_az):
    md = to_markdown(find_waste(prices, az=fake_az.path))
    assert md.splitlines()[2].startswith("| App Service plan with no apps | plan-contoso-leftover")  # biggest first
    assert "**16.46 EUR / month**" in md


def test_cli_waste_adds_untagged_and_advisor_and_can_fail_the_build(prices, fake_az, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prices", lambda args: prices)
    assert cli.main(["waste", "--az", fake_az.path]) == 0
    out = capsys.readouterr().out
    assert "microsoft.network/publicipaddresses | rg-contoso-waste | 1" in out
    assert "Azure Advisor cost recommendations\n(none)" in out
    assert cli.main(["waste", "--az", fake_az.path, "--max-waste", "5"]) == 1


def test_cli_waste_reports_az_errors(prices, fake_az, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prices", lambda args: prices)
    monkeypatch.setenv("FAKE_AZ_FAIL", "1")
    assert cli.main(["waste", "--az", fake_az.path]) == 2
    assert "az login" in capsys.readouterr().err
