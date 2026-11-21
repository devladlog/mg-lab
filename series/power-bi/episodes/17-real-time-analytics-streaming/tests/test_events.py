import json
import uuid
from collections import Counter
from datetime import datetime

import pytest

import events
from catalog import CATALOG, STORES

PRODUCTS = {code: (cat, sub, price) for cat, subs in CATALOG.items() for sub, items in subs.items() for code, _n, _c, price, _k in items}


def test_plan_is_deterministic_and_seed_dependent():
    a = events.build_plan(seed=7, minutes=3)
    assert a == events.build_plan(seed=7, minutes=3)
    assert a != events.build_plan(seed=8, minutes=3)


def test_catalog_is_the_one_of_episode_1():
    """The copy must stay a copy: same products, same stores (the star schema of episodes 1-16)."""
    import re
    from pathlib import Path
    ep1 = Path(__file__).resolve().parents[2] / "01-data-modeling-star-schema/src/data/generate_export.py"
    if not ep1.exists():
        pytest.skip("episode 1 folder not present (episode copied alone)")
    ns = {}
    text = ep1.read_text(encoding="utf-8")
    exec(compile(text[text.index("CATALOG = {"):text.index("CITIES = [")], "ep1", "exec"), ns)
    assert ns["CATALOG"] == CATALOG and ns["STORES"] == STORES


def test_every_record_has_the_kql_columns_and_consistent_values(records):
    assert set(records[0]) == set(events.FIELDS)
    assert list(records[0]) == events.FIELDS
    stores = {s[0]: s for s in STORES}
    for r in records:
        cat, sub, price = PRODUCTS[r["ProductCode"]]
        assert (r["Category"], r["Subcategory"], r["UnitPrice"]) == (cat, sub, price)
        assert r["Amount"] == round(r["Quantity"] * r["UnitPrice"], 2)
        _n, country, channel = stores[r["Store"]]
        assert (r["Country"], r["Channel"]) == (country, channel)
        assert r["Quantity"] in (1, 2, 3)
        assert r["Payment"] in ("Card", "Wallet", "Cash")
        if channel == "Online":
            assert r["Payment"] != "Cash"
        uuid.UUID(r["EventId"])
        datetime.strptime(r["EventTime"], "%Y-%m-%dT%H:%M:%S.%fZ")


def test_timestamps_are_iso_utc_with_milliseconds(records):
    assert all(len(r["EventTime"]) == len("2026-11-24T10:00:00.000Z") for r in records)


def test_duplicates_and_late_events_are_planted(plan):
    kinds = Counter(e.kind for e in plan)
    assert kinds["duplicate"] >= 1 and kinds["late"] >= 1
    ids = Counter(e.sale.event_id for e in plan)
    assert sum(1 for n in ids.values() if n == 2) == kinds["duplicate"]
    assert max(ids.values()) == 2
    for e in plan:
        if e.kind == "late":
            assert e.send_at == pytest.approx(e.sale.t + events.LATE_BY_S)
        if e.kind == "duplicate":
            assert 1 <= e.send_at - e.sale.t <= 20


def test_plan_is_in_send_order(plan):
    assert [e.send_at for e in plan] == sorted(e.send_at for e in plan)


def test_flash_sale_is_a_burst_of_online_helmets(plan):
    per_min = Counter(int(s.t // 60) for s in events.unique_sales(plan) if s.channel == "Online")
    flash = (per_min[6] + per_min[7]) / 2
    rest = [per_min[m] for m in range(10) if m not in (6, 7)]
    assert flash > 3 * (sum(rest) / len(rest))
    helmets = [s for s in events.unique_sales(plan) if s.channel == "Online" and 360 <= s.t < 480 and s.product_code == events.FLASH_PRODUCT]
    assert len(helmets) >= 50


def test_no_flash_when_the_window_is_outside_the_run():
    plan = events.build_plan(seed=1, minutes=3, flash_start_min=10)
    assert all(not (s.channel == "Online" and s.product_code == events.FLASH_PRODUCT and s.quantity > 3) for s in events.unique_sales(plan))
    assert len(events.unique_sales(plan)) < 3 * 30 * 1.3


def test_event_ids_depend_on_the_run_id():
    a = {e.sale.event_id for e in events.build_plan(seed=1, minutes=2, run_id="a")}
    b = {e.sale.event_id for e in events.build_plan(seed=1, minutes=2, run_id="b")}
    assert not a & b


def test_speed_compresses_event_time():
    from conftest import T0
    plan = events.build_plan(seed=1, minutes=2)
    s = plan[-1].sale
    assert (events.event_time(s, T0, 10) - T0).total_seconds() == pytest.approx((events.event_time(s, T0, 1) - T0).total_seconds() / 10)


@pytest.mark.parametrize("kw", [{"minutes": 0}, {"rate_per_min": 0}])
def test_bad_arguments(kw):
    with pytest.raises(ValueError):
        events.build_plan(**kw)


def test_to_json_is_compact_and_round_trips(records):
    line = events.to_json(records[0])
    assert '", "' not in line and '": ' not in line
    assert json.loads(line) == records[0]
