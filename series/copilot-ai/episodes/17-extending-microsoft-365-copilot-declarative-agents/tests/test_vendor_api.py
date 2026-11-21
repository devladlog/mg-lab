import json
import threading
import urllib.error
import urllib.request
from datetime import date

import pytest

from vendor_api.app import create_app, serve
from vendor_api.register import Register, RegisterError
from vendor_api.__main__ import main
from dakit.contract import call

TODAY = date(2026, 11, 21)


@pytest.fixture
def reg():
    return Register.load()


def test_decide_by_and_escalation_follow_the_vmo_policy(reg):
    v = reg.get_vendor("fabrikam-cloud", TODAY)
    assert v["renewalDate"] == "2027-03-31"
    assert v["decideBy"] == "2026-12-31"       # 90 days before
    assert v["escalateOn"] == "2027-01-30"     # 60 days before
    assert v["daysToDecision"] == 40


@pytest.mark.parametrize("today,status", [
    (date(2026, 11, 21), "decide-soon"),   # 40 days left, 45 or fewer
    (date(2026, 11, 1), "open"),           # 60 days left
    (date(2027, 1, 5), "overdue"),         # after decideBy, before escalateOn
    (date(2027, 1, 30), "escalated"),      # escalateOn reached
])
def test_status_over_time(reg, today, status):
    assert reg.get_vendor("fabrikam-cloud", today)["status"] == status


def test_list_is_sorted_and_total_matches_episode_2(reg):
    rows = reg.list_renewals(TODAY)
    assert [r["vendorId"] for r in rows] == ["fabrikam-cloud", "northwind-print", "adventure-works-travel", "contoso-security-labs"]
    assert sum(r["annualCostEur"] for r in rows) == 45000


def test_filters(reg):
    assert [r["vendorId"] for r in reg.list_renewals(TODAY, within_days=180)] == ["fabrikam-cloud"]
    assert [r["vendorId"] for r in reg.list_renewals(TODAY, owner="  riley demo ")] == ["northwind-print"]
    assert reg.list_renewals(TODAY, owner="Nobody Demo") == []


@pytest.mark.parametrize("bad", [0, -1, 731])
def test_within_days_range(reg, bad):
    with pytest.raises(RegisterError) as e:
        reg.list_renewals(TODAY, within_days=bad)
    assert e.value.status == 400


def test_reminder_rules(reg):
    ok = reg.create_reminder("fabrikam-cloud", {"remindOn": "2026-12-01", "note": "Decide"}, TODAY)
    assert ok == {"reminderId": "rem-0001", "vendorId": "fabrikam-cloud", "remindOn": "2026-12-01", "note": "Decide"}
    assert reg.create_reminder("fabrikam-cloud", {"remindOn": "2026-11-21"}, TODAY)["reminderId"] == "rem-0002"
    for body in ({"remindOn": "2026-11-20"}, {"remindOn": "2027-01-01"}, {"remindOn": "soon"}, {}, [], {"remindOn": "2026-12-01", "note": "x" * 201}, {"remindOn": "2026-12-01", "note": 5}):
        with pytest.raises(RegisterError) as e:
            reg.create_reminder("fabrikam-cloud", body, TODAY)
        assert e.value.status == 400
    with pytest.raises(RegisterError) as e:
        reg.create_reminder("nobody", {"remindOn": "2026-12-01"}, TODAY)
    assert e.value.status == 404
    assert len(reg.reminders) == 2   # only the valid ones were stored


@pytest.fixture
def app():
    return create_app("secret", today=lambda: TODAY)


def test_auth_required_everywhere(app):
    assert call(app, "GET", "/renewals", key=None)[0] == 401
    assert call(app, "GET", "/renewals", key="wrong")[0] == 401
    assert call(app, "GET", "/vendors/fabrikam-cloud", key="")[0] == 401
    assert call(app, "POST", "/vendors/fabrikam-cloud/reminders", body={"remindOn": "2026-12-01"}, key="nope")[0] == 401
    assert call(app, "GET", "/renewals", key="secret")[0] == 200


def test_empty_key_is_refused():
    with pytest.raises(ValueError):
        create_app("")


def test_routes_methods_and_errors(app):
    assert call(app, "GET", "/nope", key="secret")[0] == 404
    assert call(app, "POST", "/renewals", key="secret")[0] == 405
    assert call(app, "GET", "/vendors/fabrikam-cloud/reminders", key="secret")[0] == 405
    assert call(app, "DELETE", "/vendors/fabrikam-cloud", key="secret")[0] == 405
    assert call(app, "GET", "/renewals", "withinDays=abc", key="secret")[0] == 400
    status, body = call(app, "GET", "/renewals", "withinDays=0", key="secret")
    assert status == 400 and body["error"]["code"] == "invalid_request"


def test_post_body_validation(app):
    import io
    env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/vendors/fabrikam-cloud/reminders", "QUERY_STRING": "",
           "HTTP_AUTHORIZATION": "Bearer secret", "CONTENT_LENGTH": "8", "wsgi.input": io.BytesIO(b"not json")}
    got = {}
    out = b"".join(app(env, lambda s, h: got.setdefault("s", s)))
    assert got["s"].startswith("400") and b"not valid JSON" in out
    env["CONTENT_LENGTH"] = str(1024 * 1024)
    got.clear()
    b"".join(app(env, lambda s, h: got.setdefault("s", s)))
    assert got["s"].startswith("400")


def test_real_http_server_round_trip():
    """The same code behind a real socket: what Copilot (or curl) would hit through a dev tunnel."""
    server = serve("secret", "127.0.0.1", 0, today=lambda: TODAY)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        def req(method, path, body=None, key="secret"):
            r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                       data=json.dumps(body).encode() if body is not None else None,
                                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(r, timeout=5) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        s, b = req("GET", "/renewals?withinDays=180")
        assert s == 200 and b["renewals"][0]["vendorId"] == "fabrikam-cloud"
        s, b = req("POST", "/vendors/fabrikam-cloud/reminders", {"remindOn": "2026-12-01", "note": "n"})
        assert s == 201 and b["reminderId"] == "rem-0001"
        assert req("GET", "/renewals", key="bad")[0] == 401
    finally:
        server.shutdown()
        server.server_close()


def test_main_refuses_to_run_without_a_key(monkeypatch, capsys):
    monkeypatch.delenv("VENDOR_API_KEY", raising=False)
    assert main([]) == 2
    assert "VENDOR_API_KEY" in capsys.readouterr().err
