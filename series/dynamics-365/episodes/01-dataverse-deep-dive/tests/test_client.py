"""The client against the in-memory stand-in: the same HTTP code path that talks to a real environment."""
from pathlib import Path

import pytest

from dvlab import schema
from dvlab.batch import BatchItem
from dvlab.cli import import_csv, provision, report
from dvlab.client import DataverseError

CSV = Path(__file__).resolve().parents[1] / "sample" / "project-requests.csv"
KEY = {"mgl_requestcode": "PR-9001"}
ROW = {"mgl_name": "Test request", "mgl_budget": 1000.0, "mgl_priority": schema.PRIORITY["Low"]}


def test_metadata_calls_carry_the_solution_header_and_odata_headers(provisioned):
    meta = [r for r in provisioned.recorder.requests if r.method == "POST"]
    assert {r.url.split("/v9.2/")[1].split("(")[0] for r in meta} >= {"EntityDefinitions", "RelationshipDefinitions"}
    for r in meta:
        assert r.headers["MSCRM.SolutionUniqueName"] == "MGLabDataverse"
        assert r.headers["OData-Version"] == "4.0" and r.headers["Authorization"] == "Bearer t0ken"


def test_provision_waits_until_the_key_index_is_active(client):
    statuses = []
    provision(client, out=statuses.append)
    assert "  key index status: InProgress" in statuses and "  key index status: Active" in statuses
    assert client.sleeps == [10]           # one poll interval while InProgress


def test_provision_is_rerunnable(provisioned):
    lines = []
    provision(provisioned, out=lines.append)
    assert lines[0].startswith("table mgl_projectrequest already exists")


def test_upsert_before_the_key_is_active_fails(client, fake):
    client.create_table(schema.project_request_table())
    for c in schema.extra_columns():
        client.add_column(schema.TABLE, c)
    client.create_key(schema.TABLE, schema.request_code_key())
    with pytest.raises(DataverseError) as e:
        client.upsert(schema.ENTITY_SET, KEY, ROW)
    assert e.value.status == 400 and "Active" in e.value.message


def test_upsert_creates_then_updates_and_tells_which(provisioned, fake):
    assert provisioned.upsert(schema.ENTITY_SET, KEY, ROW, return_id=True) == "created"
    assert provisioned.upsert(schema.ENTITY_SET, KEY, {**ROW, "mgl_budget": 2000.0}, return_id=True) == "updated"
    rows = list(fake.rows[schema.ENTITY_SET].values())
    assert len(rows) == 1 and rows[0]["mgl_budget"] == 2000.0 and rows[0]["mgl_requestcode"] == "PR-9001"
    last = provisioned.recorder.requests[-1]
    assert last.headers["Prefer"] == "return=representation" and "$select=mgl_projectrequestid" in last.url


def test_key_columns_are_never_sent_in_the_body(provisioned):
    provisioned.upsert(schema.ENTITY_SET, KEY, {**ROW, "mgl_requestcode": "SOMETHING-ELSE"})
    assert b"mgl_requestcode" not in provisioned.recorder.requests[-1].body


def test_create_only_and_update_only(provisioned):
    with pytest.raises(DataverseError) as e:
        provisioned.upsert(schema.ENTITY_SET, KEY, ROW, mode="update-only")
    assert e.value.status == 404
    provisioned.upsert(schema.ENTITY_SET, KEY, ROW, mode="create-only")
    with pytest.raises(DataverseError) as e:
        provisioned.upsert(schema.ENTITY_SET, KEY, ROW, mode="create-only")
    assert e.value.status == 412
    assert provisioned.recorder.requests[-1].headers["If-None-Match"] == "*"


def test_paging_follows_next_link_verbatim_with_the_same_page_size(provisioned):
    import_csv(provisioned, CSV, out=lambda s: None)
    before = len(provisioned.recorder.requests)
    pages = list(provisioned.query(schema.ENTITY_SET, select=["mgl_requestcode"], orderby="mgl_requestcode asc",
                                   page_size=4))
    assert [len(p) for p in pages] == [4, 4, 4, 4, 2]
    gets = provisioned.recorder.requests[before:]
    assert all(g.headers["Prefer"].startswith("odata.maxpagesize=4") for g in gets)
    assert "$skiptoken=" in gets[1].url and "$skip=" not in gets[1].url
    codes = [r["mgl_requestcode"] for p in pages for r in p]
    assert codes == sorted(codes) and len(set(codes)) == len(codes)


def test_page_size_above_5000_is_refused(provisioned):
    with pytest.raises(ValueError):
        next(provisioned.query(schema.ENTITY_SET, select=["mgl_name"], page_size=5001))


def test_429_waits_for_retry_after_then_succeeds(make_client, fake):
    fake.throttle_every, fake.retry_after = 3, 7
    c = make_client()
    provision(c, out=lambda s: None)
    assert c.retries_done >= 1
    assert 7.0 in c.sleeps


def test_429_without_retry_after_backs_off_exponentially(make_client, monkeypatch):
    c = make_client(max_retries=3)

    class Always429:
        status_code, headers, text = 429, {}, "{}"

        def json(self):
            return {"error": {"code": "0x80072326", "message": "Number of concurrent requests exceeded the limit of 52."}}

    monkeypatch.setattr(c.session, "request", lambda *a, **k: Always429())
    with pytest.raises(DataverseError) as e:
        c.request("GET", "WhoAmI")
    assert e.value.status == 429 and c.sleeps == [1.0, 2.0, 4.0]


def test_changeset_is_all_or_nothing(provisioned, fake):
    items = [BatchItem("PATCH", f"{schema.ENTITY_SET}(mgl_requestcode='PR-1')", ROW),
             BatchItem("PATCH", f"{schema.ENTITY_SET}(mgl_requestcode='PR-2')", {**ROW, "mgl_budget": -1.0})]
    with pytest.raises(DataverseError):
        provisioned.batch(items, changeset=True)
    assert fake.rows[schema.ENTITY_SET] == {}            # PR-1 was rolled back


def test_batch_without_changeset_and_continue_on_error_keeps_good_rows(provisioned, fake):
    items = [BatchItem("PATCH", f"{schema.ENTITY_SET}(mgl_requestcode='PR-1')", ROW),
             BatchItem("PATCH", f"{schema.ENTITY_SET}(mgl_requestcode='PR-2')", {**ROW, "mgl_budget": -1.0}),
             BatchItem("PATCH", f"{schema.ENTITY_SET}(mgl_requestcode='PR-3')", ROW)]
    results = provisioned.batch(items, changeset=False, continue_on_error=True)
    assert [r.status for r in results] == [204, 400, 204]
    assert len(fake.rows[schema.ENTITY_SET]) == 2


def test_import_is_idempotent_and_reports_bad_rows(provisioned, fake):
    log = []
    first = import_csv(provisioned, CSV, batch_size=8, out=log.append)
    assert first == {"rows": 21, "sent": 20, "ok": 19, "rejected_locally": 1, "failed": 1, "distinct": 18}
    assert any("PR/0019" in line and "SKIPPED" in line for line in log)
    assert any("PR-0018" in line and "FAILED" in line for line in log)
    import_csv(provisioned, CSV, batch_size=8, out=lambda s: None)
    assert len(fake.rows[schema.ENTITY_SET]) == 18      # second run updated, didn't duplicate


def test_report_counts_high_budget_requests_across_pages(provisioned):
    import_csv(provisioned, CSV, out=lambda s: None)
    lines = []
    assert report(provisioned, min_budget=50000, page_size=3, out=lines.append) == 10
    assert [line for line in lines if line.startswith("page")] == ["page 1: 3 rows", "page 2: 3 rows",
                                                                   "page 3: 3 rows", "page 4: 1 rows"]


def test_errors_surface_status_and_message(provisioned):
    with pytest.raises(DataverseError) as e:
        provisioned.upsert(schema.ENTITY_SET, KEY, {**ROW, "mgl_nosuchcolumn": 1})
    assert e.value.status == 400 and "mgl_nosuchcolumn" in e.value.message


def test_key_failed_status_raises(client, fake, monkeypatch):
    monkeypatch.setattr(client, "key_status", lambda t, k: "Failed")
    with pytest.raises(DataverseError, match="ReactivateEntityKey"):
        client.wait_for_key(schema.TABLE, schema.KEY_SCHEMA)
