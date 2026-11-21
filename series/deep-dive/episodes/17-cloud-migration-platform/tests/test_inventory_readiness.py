import pytest

from migplan import inventory, readiness
from migplan.inventory import Server


def codes(findings, server):
    return {f.code for f in findings if f.server == server}


def test_cmdb_loads_with_connections(cmdb):
    assert len(cmdb.servers) == 14
    assert cmdb.connections


def test_duplicate_names_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        inventory.from_dict({"servers": [{"name": "A"}, {"name": "a"}]})


def test_infrastructure_ports_do_not_create_edges(cmdb):
    edges = inventory.dependency_edges(cmdb)
    flat = {n for e in edges for n in e}
    assert "dc01" not in flat and "mon01" not in flat      # everyone talks to them on 53/88/389/445/5985
    assert frozenset({"app01", "sql01"}) in edges
    assert frozenset({"build01", "nexus01"}) in edges


def test_unknown_destination_ignored(cmdb):
    # web01 -> 52.0.0.1:443 is not in the inventory
    assert all("52.0.0.1" not in str(e) for e in inventory.dependency_edges(cmdb))


def test_legacy_server_without_memory_is_blocked(cmdb):
    f = readiness.check_inventory(cmdb)
    assert "missing-field" in codes(f, "legacy01")
    assert "missing-field" not in codes(f, "sql01")


def test_end_of_support_is_a_warning_not_a_blocker(cmdb):
    f = readiness.check_inventory(cmdb)
    eos = {x.server for x in f if x.code == "os-end-of-support"}
    assert eos == {"rep01", "legacy01", "sqlold01"}
    assert all(x.severity == "warning" for x in f if x.code == "os-end-of-support")


def test_unrecognised_os_name_blocks():
    s = Server("x", cores=2, memory_mb=4096, os_name="Plan 9 from Bell Labs", disks_gb=[10], cpu_util_pct=1, mem_util_pct=1)
    assert "os-name-not-recognised" in {f.code for f in readiness.check_server(s)}


def test_os_name_matching_is_by_containment():
    s = Server("x", cores=2, memory_mb=4096, os_name="Microsoft Windows Server 2019 Datacenter", os_version="10", disks_gb=[10])
    assert "os-name-not-recognised" not in {f.code for f in readiness.check_server(s)}


def test_landing_zone_overlap_detected(cmdb):
    assert not [f for f in readiness.check_inventory(cmdb, ("10.60.0.0/16",)) if f.code == "address-overlaps-landing-zone"]
    overlap = [f for f in readiness.check_inventory(cmdb, ("10.20.0.0/16",)) if f.code == "address-overlaps-landing-zone"]
    assert len(overlap) == 14


def test_twenty_one_disks_blocks():
    s = Server("x", cores=2, memory_mb=4096, os_name="Ubuntu Linux 22.04", disks_gb=[1] * 21)
    assert "too-many-disks" in {f.code for f in readiness.check_server(s)}


def test_utilisation_must_be_a_percentage():
    s = Server("x", cores=2, memory_mb=4096, os_name="Ubuntu Linux", cpu_util_pct=140, mem_util_pct=5)
    assert "utilisation-out-of-range" in {f.code for f in readiness.check_server(s)}


def test_importable_excludes_blocked(cmdb):
    f = readiness.check_inventory(cmdb)
    names = {s.name for s in readiness.importable(cmdb, f)}
    assert "legacy01" not in names and len(names) == 13
