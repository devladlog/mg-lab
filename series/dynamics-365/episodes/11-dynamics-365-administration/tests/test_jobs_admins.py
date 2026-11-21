import datetime as dt

from adminkit import admins, cli, jobs
from conftest import FakeResponse, sample

NOW = dt.datetime(2027, 1, 15, 12, 0, tzinfo=dt.timezone.utc)


def test_failed_jobs_are_grouped_by_type_and_message(cfg):
    f = [x for x in jobs.analyse(sample("system-jobs.json")["value"], NOW, cfg) if x.rule == "J001"]
    assert [(x.subject, x.message.split(" failed")[0]) for x in f] == [("Workflow", "3"), ("Bulk Delete", "1")]
    assert all(x.level == "error" for x in f)


def test_failures_outside_the_window_are_ignored(cfg):
    msgs = " ".join(x.message for x in jobs.analyse(sample("system-jobs.json")["value"], NOW, cfg))
    assert "old." not in msgs


def test_stuck_job_is_flagged_but_postponed_and_recent_ones_are_not(cfg):
    w = [x for x in jobs.analyse(sample("system-jobs.json")["value"], NOW, cfg) if x.rule == "J002"]
    assert len(w) == 1 and "Nightly import" in w[0].subject and "38 h" in w[0].message


def test_first_line_of_the_message_is_used():
    j = jobs.to_job({"name": "x", "operationtype": 10, "statuscode": 31, "friendlymessage": "line one\nline two"})
    assert j.text == "line one" and j.op_type == "type 10"


def test_query_asks_for_both_failed_and_open_jobs():
    q = jobs.query(NOW, 7, 24)
    assert "statuscode eq 31 and completedon ge 2027-01-08T12:00:00Z" in q
    assert "statuscode eq 0 or statuscode eq 10 or statuscode eq 20" in q and "createdon le 2027-01-14T12:00:00Z" in q


def test_fetch_follows_paging_and_asks_for_formatted_values(api, stub, cfg):
    page = {"value": sample("system-jobs.json")["value"][:2], "@odata.nextLink": None}
    stub.on("GET", r"^asyncoperations\?", FakeResponse(200, page))
    assert len(jobs.fetch(api, NOW, cfg)) == 2
    assert "FormattedValue" in stub.sent("GET")[0]["headers"]["Prefer"]


def roles():
    return sample("system-administrators.json")["value"]


def test_admin_findings(cfg):
    f = {x.rule: x for x in admins.analyse(roles(), cfg)}
    assert f["A001"].level == "error" and "4 enabled people" in f["A001"].message
    assert f["A002"].subject == "Riley Demo"
    assert f["A003"].subject == "Contoso Platform Team"
    assert f["A004"].level == "info" and "2 application" in f["A004"].message


def test_application_users_do_not_count_as_people(cfg):
    cfg["admins"]["max_human_admins"] = 4
    assert "A001" not in {x.rule for x in admins.analyse(roles(), cfg)}


def test_a_user_in_two_business_units_is_counted_once(cfg):
    r = roles()
    r.append({"roleid": "x", "name": "System Administrator", "systemuserroles_association": [r[0]["systemuserroles_association"][0]],
              "teamroles_association": []})
    users, _ = admins.holders(r)
    assert len(users) == 7


def test_role_query_expands_both_associations_and_quotes_the_name():
    q = admins.query("O'Brien Admin")
    assert "name eq 'O''Brien Admin'" in q and "systemuserroles_association(" in q and "teamroles_association(" in q


def test_cli_exit_code_is_1_on_errors_and_0_when_clean(tmp_path, cfg, capsys):
    sample_dir = cli.EPISODE / "sample"
    assert cli.main(["admins", "--from-json", str(sample_dir / "system-administrators.json")]) == 1
    clean = tmp_path / "clean.json"
    clean.write_text('{"value":[{"name":"System Administrator","systemuserroles_association":[],"teamroles_association":[]}]}')
    assert cli.main(["admins", "--from-json", str(clean)]) == 0
    assert "0 error(s)" in capsys.readouterr().out
