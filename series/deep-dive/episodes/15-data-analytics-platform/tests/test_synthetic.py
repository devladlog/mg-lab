import pandas as pd
import sqlglot
from sqlglot import exp

from analytics import synthetic as syn


def test_history_is_deterministic():
    a, b = syn.generate_history(300), syn.generate_history(300)
    pd.testing.assert_frame_equal(a, b)
    assert a["RequestId"].is_unique and len(a) == 300


def test_snapshot_only_contains_requests_already_submitted(history):
    s = syn.snapshot(history, syn.T1)
    assert (s["SubmittedOn"] <= syn.T1).all()
    assert (s["ModifiedOn"] <= syn.T1).all()


def test_undecided_requests_are_submitted_without_approval_date(history):
    s = syn.snapshot(history, syn.T1)
    open_ = s[s["Status"] == "Submitted"]
    assert len(open_) > 0
    assert open_["ApprovedOn"].isna().all()
    assert (open_["ModifiedOn"] == open_["SubmittedOn"]).all()


def test_rejected_requests_have_no_approval_date(history):
    s = syn.snapshot(history, syn.T2)
    assert s.loc[s["Status"] == "Rejected", "ApprovedOn"].isna().all()
    assert s.loc[s["Status"] == "Approved", "ApprovedOn"].notna().all()


def test_delta_is_exactly_the_rows_modified_between_the_watermarks(history):
    first, second = syn.delta(history, None, syn.T1), syn.delta(history, syn.T1, syn.T2)
    assert (second["ModifiedOn"] > syn.T1).all() and (second["ModifiedOn"] <= syn.T2).all()
    # the second load both updates requests the first load had as 'Submitted' and brings new ones
    ids1, ids2 = set(first["RequestId"]), set(second["RequestId"])
    assert ids1 & ids2, "some requests must be updated by the second load (that is what makes silver necessary)"
    assert ids2 - ids1, "and some must be new"
    updated = second[second["RequestId"].isin(ids1)]
    assert (updated["Status"] != "Submitted").all()


def test_merge_script_parses_as_tsql_and_carries_every_row(history):
    df = syn.delta(history, syn.T1, syn.T2)
    script = syn.to_merge_sql(df, batch=50)
    batches = [b for b in script.split("\nGO\n") if "MERGE" in b]
    rows = 0
    for b in batches:
        tree = sqlglot.parse_one(b.replace("SET NOCOUNT ON;", ""), read="tsql")
        assert isinstance(tree, exp.Merge)
        rows += len(list(tree.find(exp.Values).expressions))
    assert rows == len(df)
    assert "N'FIN'" in script or "N'IT'" in script


def test_defects_are_four_distinct_bad_rows(history):
    d = syn.inject_defects(syn.delta(history, None, syn.T1))
    assert set(d["RequestId"]) >= {9001, 9002, 9003, 9004}


def test_phase_three_defects_are_newer_than_the_second_load_so_the_watermark_picks_them_up(history):
    bad = syn.defect_rows(syn.delta(history, None, syn.T1), modified_on=syn.T3)
    assert len(bad) == 4 and (bad["ModifiedOn"] > syn.T2).all()
    assert bad["RequestId"].is_unique
