import pytest

from migplan import readiness, sizing, waves
from migplan.inventory import Server, from_dict


def srv(**kw):
    base = dict(name="s", cores=4, memory_mb=16384, os_name="Windows Server 2022", cpu_util_pct=50, mem_util_pct=50)
    base.update(kw)
    return Server(**base)


def test_catalog_matches_learn_specs():
    d = {s.vcpus: s.memory_gib for s in sizing.CATALOG if s.family == "D"}
    e = {s.vcpus: s.memory_gib for s in sizing.CATALOG if s.family == "E"}
    assert d == {2: 8, 4: 16, 8: 32, 16: 64, 32: 128}
    assert e == {2: 16, 4: 32, 8: 64, 16: 128, 32: 256}


def test_as_is_uses_allocation():
    r = sizing.recommend(srv(cpu_util_pct=None, mem_util_pct=None))
    assert r.mode == "as-is" and r.sku.name == "Standard_D4s_v5"


def test_performance_uses_utilisation_times_comfort():
    r = sizing.recommend(srv(cores=8, memory_mb=32768, cpu_util_pct=25, mem_util_pct=25), comfort=1.3)
    assert r.mode == "performance"
    assert r.need_cores == pytest.approx(2.6) and r.need_memory_gib == pytest.approx(10.4)
    assert r.sku.name == "Standard_D4s_v5"


def test_comfort_factor_can_change_the_size():
    low = sizing.recommend(srv(cores=8, memory_mb=32768, cpu_util_pct=50, mem_util_pct=50), comfort=1.0)
    high = sizing.recommend(srv(cores=8, memory_mb=32768, cpu_util_pct=50, mem_util_pct=50), comfort=2.0)
    assert low.sku.vcpus < high.sku.vcpus


def test_memory_heavy_goes_to_e_family():
    r = sizing.recommend(srv(cores=2, memory_mb=65536, cpu_util_pct=None, mem_util_pct=None))
    assert r.sku.family == "E"


def test_too_big_and_missing_data():
    assert sizing.recommend(srv(cores=64, cpu_util_pct=None, mem_util_pct=None)).sku is None
    assert sizing.recommend(srv(memory_mb=None)).sku is None


def test_never_less_than_one_core():
    assert sizing.recommend(srv(cpu_util_pct=0, mem_util_pct=0)).need_cores == 1.0


def test_shared_services_do_not_merge_everything_into_one_wave(cmdb):
    plan = waves.plan_waves(cmdb, readiness.check_inventory(cmdb))
    assert plan.foundation == ["dc01", "dc02", "mon01"]
    sizes = sorted(len(w.servers) for w in plan.waves)
    assert max(sizes) == 6 and len(plan.waves) == 4   # app tier + db + rep01 + web stay together, the rest are separate


def test_without_the_infra_port_filter_everything_would_merge(cmdb):
    from migplan.inventory import dependency_edges
    naive = dependency_edges(cmdb, ignore_ports=frozenset())
    comps = waves._components([s.name for s in cmdb.servers], naive)
    assert max(len(c) for c in comps) >= 13     # one blob: this is the problem the filter solves


def test_app_and_database_share_a_wave(cmdb):
    plan = waves.plan_waves(cmdb, readiness.check_inventory(cmdb))
    wave = next(w for w in plan.waves if "sql01" in w.servers)
    assert {"app01", "app02", "web01", "web02", "rep01"} <= set(wave.servers)
    assert wave.criticality == "high"


def test_pilot_is_lowest_criticality_smallest(cmdb):
    plan = waves.plan_waves(cmdb, readiness.check_inventory(cmdb))
    assert plan.waves[0].name == "pilot" and plan.waves[0].criticality == "low"
    assert len(plan.waves[0].servers) == 1
    assert [w.criticality for w in plan.waves] == sorted((w.criticality for w in plan.waves), key=["low", "medium", "high"].index)


def test_blocked_server_is_reported_with_its_partner(cmdb):
    plan = waves.plan_waves(cmdb, readiness.check_inventory(cmdb))
    assert plan.blocked == ["legacy01"]
    assert any("legacy01" in w and "sqlold01" in w for w in plan.warnings)
    assert all("legacy01" not in w.servers for w in plan.waves)


def test_oversized_group_is_noted_not_split(cmdb):
    plan = waves.plan_waves(cmdb, readiness.check_inventory(cmdb), max_wave_size=3)
    big = next(w for w in plan.waves if "sql01" in w.servers)
    assert len(big.servers) == 6 and big.notes


def test_empty_inventory():
    plan = waves.plan_waves(from_dict({"servers": []}))
    assert plan.waves == [] and plan.foundation == []
