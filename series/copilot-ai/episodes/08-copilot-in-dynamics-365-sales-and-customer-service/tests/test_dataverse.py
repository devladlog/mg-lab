import urllib.parse

import pytest

from d365_copilot_ready.dataverse import DataverseClient, DataverseError, mask_org_url


def test_mask_org_url_hides_the_org_name():
    assert mask_org_url("https://contoso.crm4.dynamics.com/") == "https://***.crm4.dynamics.com"
    assert mask_org_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"


def test_client_rules_and_token_never_in_repr():
    with pytest.raises(ValueError):
        DataverseClient("http://contoso.crm4.dynamics.com", "t")
    with pytest.raises(ValueError):
        DataverseClient("https://contoso.crm4.dynamics.com", "")
    with pytest.raises(ValueError):
        DataverseClient("https://contoso.crm4.dynamics.com", "t", page_size=5001)
    c = DataverseClient("https://contoso.crm4.dynamics.com", "secret-token")
    assert "secret-token" not in repr(c) and "contoso" not in repr(c)


def test_paging_follows_next_link_and_sends_documented_headers(fake):
    with fake() as srv:
        c = DataverseClient(srv.url, "tok", page_size=2)
        rows = list(c.get_all("incidents", ["incidentid", "title"]))
    assert [r["ticketnumber"] for r in rows] == [f"CAS-100{i}" for i in range(1, 7)]
    assert len(srv.requests) == 3  # 6 rows, 2 per page
    first = srv.requests[0]
    h = {k.lower(): v for k, v in first["headers"].items()}  # urllib normalises header name case
    assert h["authorization"] == "Bearer tok"
    assert h["prefer"] == "odata.maxpagesize=2"
    assert h["odata-maxversion"] == "4.0" and h["odata-version"] == "4.0"
    assert "$select=incidentid,title" in first["path"]
    # Learn: no $skip, and later pages repeat the same page size preference
    assert all("$skip=" not in r["path"] for r in srv.requests)
    assert all({k.lower(): v for k, v in r["headers"].items()}["prefer"] == "odata.maxpagesize=2" for r in srv.requests)
    assert "$skiptoken=2" in srv.requests[1]["path"] and "$skiptoken=4" in srv.requests[2]["path"]


def test_filter_is_url_encoded(fake):
    with fake() as srv:
        list(DataverseClient(srv.url, "t").get_all("annotations", filter="objecttypecode eq 'incident'"))
    path = srv.requests[0]["path"]
    assert " " not in path
    assert urllib.parse.unquote(path).endswith("$filter=objecttypecode eq 'incident'")


def test_http_error_becomes_dataverse_error_without_token(fake):
    with fake(fail_with=403) as srv:
        with pytest.raises(DataverseError) as e:
            list(DataverseClient(srv.url, "super-secret").get_all("accounts"))
    assert "403" in str(e.value) and "not authorised" in str(e.value)
    assert "super-secret" not in str(e.value)


def test_paging_loop_is_detected(fake):
    with fake(loop=True) as srv:
        with pytest.raises(DataverseError, match="paging loop"):
            list(DataverseClient(srv.url, "t", page_size=1).get_all("accounts"))
