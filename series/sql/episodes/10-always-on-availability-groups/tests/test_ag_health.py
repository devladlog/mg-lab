"""ag_health.assess: one test per rule."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ag_health as ah  # noqa: E402


def row(name="CON-SQL02", role="SECONDARY", mode="SYNCHRONOUS_COMMIT", fmode="AUTOMATIC", conn="CONNECTED",
        state="SYNCHRONIZED", health="HEALTHY", susp=0, send=0, redo=0):
    return (name, role, mode, fmode, conn, state, health, susp, send, redo)


def one(**kw):
    return ah.assess([row(**kw)])[0]


PRIMARY_ROW = row("CON-SQL01", role="PRIMARY", send=None, redo=None)


def test_synchronized_automatic_secondary_is_failover_ready():
    v = one()
    assert v.verdict == ah.AUTO and "no data loss" in v.reason


def test_manual_failover_mode_is_manual_ready():
    assert one(fmode="MANUAL").verdict == ah.MANUAL


def test_asynchronous_commit_can_lose_data_even_when_synchronizing_looks_fine():
    v = one(mode="ASYNCHRONOUS_COMMIT", state="SYNCHRONIZING", fmode="MANUAL")
    assert v.verdict == ah.LOSS and "forced" in v.reason


def test_synchronous_but_still_synchronizing_can_lose_data():
    v = one(state="SYNCHRONIZING")
    assert v.verdict == ah.LOSS and "SYNCHRONIZING" in v.reason


def test_not_synchronizing_is_data_loss_possible_too():
    assert one(state="NOT SYNCHRONIZING", health="NOT_HEALTHY").verdict == ah.LOSS


def test_disconnected_replica_is_not_ready():
    v = one(conn="DISCONNECTED", state=None, health=None)
    assert v.verdict == ah.NOT_READY and "DISCONNECTED" in v.reason


def test_unknown_connection_state_is_not_ready():
    assert one(conn=None).verdict == ah.NOT_READY


def test_missing_database_row_means_seeding_has_not_started():
    v = one(state=None, health=None, susp=None)
    assert v.verdict == ah.NOT_READY and "seeding" in v.reason


def test_suspended_is_not_ready_even_if_it_says_synchronized():
    v = one(susp=1)
    assert v.verdict == ah.NOT_READY and "suspended" in v.reason


def test_unhealthy_but_synchronized_is_not_ready():
    assert one(health="PARTIALLY_HEALTHY").verdict == ah.NOT_READY


def test_primary_row_is_reported_as_primary():
    assert ah.assess([PRIMARY_ROW])[0].verdict == ah.PRIMARY


def test_summary_variants():
    assert ah.summary(ah.assess([PRIMARY_ROW, row()])).startswith("FAILOVER READY, NO DATA LOSS (automatic)")
    assert ah.summary(ah.assess([PRIMARY_ROW, row(fmode="MANUAL")])).endswith("(manual)")
    bad = ah.summary(ah.assess([PRIMARY_ROW, row(state="SYNCHRONIZING")]))
    assert bad.startswith("NOT SAFE TO FAIL OVER") and "CON-SQL02 DATA LOSS POSSIBLE" in bad
    assert ah.summary(ah.assess([row()])).startswith("NO PRIMARY")
    assert ah.summary(ah.assess([PRIMARY_ROW])).startswith("NO SECONDARY")


def test_render_lists_replicas_then_the_summary():
    out = ah.render(ah.assess([PRIMARY_ROW, row()])).splitlines()
    assert len(out) == 3 and out[0].startswith("CON-SQL01") and out[-1].startswith("FAILOVER READY")
    assert ah.render([]) == "(no replicas)"


def test_accepts_replica_objects_and_keeps_queue_sizes():
    r = ah.Replica.from_row(row(send=12, redo=34))
    assert (r.log_send_queue_kb, r.redo_queue_kb) == (12, 34)
    assert ah.assess([r])[0].verdict == ah.AUTO
