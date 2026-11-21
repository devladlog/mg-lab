import json

from d365_copilot_ready import cli
from d365_copilot_ready.dataset import analyse, load_sample

from conftest import SAMPLE


def test_sample_totals_are_stable():
    findings, s = analyse(load_sample(SAMPLE))
    assert (s["opportunities"], s["accounts"], s["cases"], s["articles"]) == (6, 4, 6, 7)
    assert (s["errors"], s["warnings"], s["info"]) == (7, 11, 9)
    assert s["articles_usable_for_ui_language"] == 2  # KA-0001 and KA-0007 (warnings only)


def test_each_sample_record_has_the_intended_finding():
    findings, _ = analyse(load_sample(SAMPLE))
    by = {}
    for f in findings:
        by.setdefault(f.record.split(" ")[0] if f.entity != "opportunity" else f.record, set()).add(f.code)
    assert "CAS-1001" not in by and "CAS-1006" not in by          # clean cases
    assert "CAS-1003" not in by                                   # short description rescued by notes and email
    assert by["CAS-1002"] == {"C001"}
    assert by["CAS-1004"] == {"C004", "C005", "C006"}
    assert by["CAS-1005"] == {"C003"}
    assert by["KA-0002"] == {"K001"} and by["KA-0003"] == {"K002"} and by["KA-0004"] == {"K003"}
    assert by["KA-0005"] == {"K005"} and by["KA-0006"] == {"K004"} and by["KA-0007"] == {"K005", "K006"}
    assert "KA-0001" not in by
    assert by["Proseware courier trial"] == {"O004", "O005", "O007"}
    assert "Tailspin fleet: 40 e-bikes" not in by


def test_other_ui_language_changes_the_usable_articles():
    _, s = analyse(load_sample(SAMPLE), ui_localeid=2070)
    assert s["articles_usable_for_ui_language"] == 1  # only the Portuguese article


def test_cli_text_and_exit_codes(capsys):
    assert cli.main(["check", "--sample", str(SAMPLE)]) == 1
    out = capsys.readouterr().out
    assert "-- 7 errors, 11 warnings, 9 info" in out
    assert out.index("ERROR") < out.index("WARNING") < out.index("INFO")
    assert cli.main(["check", "--sample", str(SAMPLE), "--fail-on", "never"]) == 0


def test_cli_json(capsys):
    cli.main(["check", "--sample", str(SAMPLE), "--format", "json", "--fail-on", "never"])
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["errors"] == 7
    assert {"severity", "code", "entity", "record", "message"} <= set(data["findings"][0])


def test_cli_live_needs_a_token_and_does_not_print_it(capsys, monkeypatch):
    monkeypatch.delenv("DATAVERSE_TOKEN", raising=False)
    assert cli.main(["check", "--org", "https://contoso.crm4.dynamics.com"]) == 2
    assert "DATAVERSE_TOKEN" in capsys.readouterr().err


def test_cli_live_against_local_paging_server_matches_sample(fake, capsys, monkeypatch):
    monkeypatch.setenv("DATAVERSE_TOKEN", "tok")
    with fake() as srv:
        rc = cli.main(["check", "--org", srv.url, "--page-size", "2", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    _, expected = analyse(load_sample(SAMPLE))
    assert data["summary"] == expected
    # one request per page per entity set: 9 entity sets, several of them paged
    assert len(srv.requests) > 9
    assert any("annotations?" in r["path"] and "objecttypecode" in r["path"] for r in srv.requests)


def test_cli_live_error_is_reported_cleanly(fake, capsys, monkeypatch):
    monkeypatch.setenv("DATAVERSE_TOKEN", "tok")
    with fake(fail_with=401) as srv:
        assert cli.main(["check", "--org", srv.url]) == 2
    assert "401" in capsys.readouterr().err
