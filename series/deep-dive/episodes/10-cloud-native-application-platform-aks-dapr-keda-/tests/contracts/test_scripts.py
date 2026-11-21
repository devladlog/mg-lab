import json
import re
import uuid
from pathlib import Path

import pytest

from conftest import ROOT

import sys
sys.path.insert(0, str(ROOT / "scripts"))
import render_manifests  # noqa: E402
import send_burst  # noqa: E402


# ---- render_manifests ------------------------------------------------------------------------------------------------------
def test_render_fills_tokens_and_leaves_the_rest():
    assert render_manifests.render("a: {{x}}\nb: {{ y }}\nc: z", {"x": "1", "y": "2"}) == "a: 1\nb: 2\nc: z"


def test_render_refuses_missing_and_empty_values():
    with pytest.raises(ValueError, match="no value for token.*y"):
        render_manifests.render("{{x}} {{y}}", {"x": "1"})
    with pytest.raises(ValueError, match="x"):
        render_manifests.render("{{x}}", {"x": "  "})


def test_outputs_accept_the_az_shape_and_a_flat_map(tmp_path):
    f = tmp_path / "o.json"
    f.write_text(json.dumps({"a": {"type": "String", "value": "1"}, "b": "2"}))
    assert render_manifests.load_outputs(f) == {"a": "1", "b": "2"}


def test_cli_exits_1_and_writes_nothing_useful_when_a_value_is_missing(tmp_path, capsys):
    f = tmp_path / "o.json"
    f.write_text(json.dumps({"appClientId": "x"}))
    rc = render_manifests.main(["--outputs", str(f), "--image", "img:1", "--out", str(tmp_path / "out")])
    assert rc == 1
    assert "no value for token" in capsys.readouterr().err


# ---- send_burst -------------------------------------------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_request_is_a_service_bus_rest_send_with_broker_properties():
    ev = send_burst.make_event(1, __import__("random").Random(1))
    mid = str(uuid.uuid4())
    req = send_burst.build_request("sb-x", "purchase-events", "TOKEN", ev, mid)
    assert req.full_url == "https://sb-x.servicebus.windows.net/purchase-events/messages"
    assert req.get_method() == "POST"
    h = {k.lower(): v for k, v in req.header_items()}
    assert h["authorization"] == "Bearer TOKEN" and h["content-type"] == "application/json"
    broker = json.loads(h["brokerproperties"])
    assert broker["MessageId"] == mid and broker["Label"] == "purchase.high"
    assert json.loads(req.data) == ev


def test_every_generated_event_passes_the_workers_rules():
    import random
    rng = random.Random(7)
    for n in range(200):
        e = send_burst.make_event(n, rng)
        assert re.fullmatch(r"PR-[0-9]{4,8}", e["purchaseRequestId"])
        assert 5000 <= e["total"] <= 20000 and e["currency"] == "EUR" and e["eventType"] == "submitted"
        assert len(e["note"]) <= 500


def test_main_sends_count_messages_with_unique_ids_and_succeeds_on_201(capsys):
    seen = []

    def opener(req, timeout):
        seen.append(json.loads(req.headers["Brokerproperties"])["MessageId"])
        return FakeResponse(201)

    rc = send_burst.main(["--namespace", "sb-x", "--count", "25"], token_fn=lambda: "t", opener=opener)
    assert rc == 0 and len(seen) == 25 and len(set(seen)) == 25
    assert "sent 25/25" in capsys.readouterr().out


def test_main_fails_when_the_service_says_no(capsys):
    import urllib.error

    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    rc = send_burst.main(["--namespace", "sb-x", "--count", "3"], token_fn=lambda: "t", opener=opener)
    assert rc == 1
    assert "401" in capsys.readouterr().out


def test_same_seed_same_events():
    def first_ids(seed):
        ids = []
        send_burst.main(["--namespace", "n", "--count", "5", "--seed", str(seed), "--workers", "1"], token_fn=lambda: "t",
                        opener=lambda req, timeout: (ids.append(req.headers["Brokerproperties"]), FakeResponse(201))[1])
        return ids
    assert first_ids(3) == first_ids(3) != first_ids(4)


def test_count_is_bounded():
    with pytest.raises(SystemExit):
        send_burst.main(["--namespace", "n", "--count", "0"], token_fn=lambda: "t")


def test_poison_messages_are_sent_and_are_invalid_for_the_worker(capsys):
    bodies = []

    def opener(req, timeout):
        bodies.append(json.loads(req.data))
        return FakeResponse(201)

    rc = send_burst.main(["--namespace", "n", "--count", "4", "--poison", "2", "--workers", "1"], token_fn=lambda: "t", opener=opener)
    assert rc == 0 and len(bodies) == 6
    assert sum(1 for b in bodies if "total" not in b) == 2          # the two poison bodies lack the required fields
    assert "sent 6/6" in capsys.readouterr().out
