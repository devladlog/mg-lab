from datetime import date

import pytest

from bpfkit import path, report

A, B, C, D = "aaaa", "bbbb", "cccc", "dddd"


def test_forward_appends_the_next_stage_of_the_active_path():
    mv = path.forward([A, B, C], A, A)
    assert mv.target == B and mv.traversedpath == "aaaa,bbbb"
    assert mv.payload() == {"activestageid@odata.bind": "/processstages(bbbb)", "traversedpath": "aaaa,bbbb"}


def test_forward_follows_the_branch_the_server_evaluated():
    # budget under 50,000: RetrieveActivePath skips Finance Review (B), so Submit (A) -> Approve (C)
    assert path.forward([A, C, D], A, A).target == C


def test_forward_at_last_stage_says_use_finish():
    with pytest.raises(path.StageMoveError, match="finish"):
        path.forward([A, B], B, "aaaa,bbbb")


def test_back_returns_to_the_previously_visited_stage_and_trims_the_path():
    mv = path.back([A, C, D], C, "aaaa,cccc")
    assert mv.target == A and mv.traversedpath == "aaaa"


def test_back_at_first_stage_is_refused():
    with pytest.raises(path.StageMoveError, match="first stage"):
        path.back([A, B], A, A)


def test_active_stage_not_on_active_path_is_refused():
    # the record was in Finance Review, then someone lowered the budget: the branch no longer includes it
    with pytest.raises(path.StageMoveError, match="branch"):
        path.forward([A, C, D], B, "aaaa,bbbb")


def test_traversed_path_not_ending_at_active_stage_is_refused():
    with pytest.raises(path.StageMoveError, match="inconsistent"):
        path.forward([A, B, C], B, "aaaa")


def test_guids_are_normalised_braces_and_case():
    mv = path.forward(["{AAAA}", "BBBB"], "aaaa", "{AAAA}")
    assert mv.traversedpath == "aaaa,bbbb"
    assert path.parse_traversed(" aaaa, ,BBBB ") == ["aaaa", "bbbb"]


def test_can_finish_only_at_last_stage_and_state_names():
    assert path.can_finish([A, B], B) and not path.can_finish([A, B], A) and not path.can_finish([], A)
    assert path.state_name(0, 1) == "Active" and path.state_name(0, 2) == "Finished"
    assert path.state_name(1, 3) == "Aborted" and path.state_name(1, 9) == "state 1/9"


def test_parse_day_accepts_date_and_datetime():
    assert report.parse_day("2027-01-05T23:30:00Z") == date(2027, 1, 5)
    assert report.parse_day("2027-01-05") == date(2027, 1, 5)
    assert report.parse_day(None) is None


def rows():
    R = report.Row
    return [R("PR-1", "Submit", "Active", date(2027, 1, 14)), R("PR-2", "Finance Review", "Active", date(2027, 1, 10)),
            R("PR-3", "Finance Review", "Active", date(2027, 1, 13)), R("PR-4", "Approve", "Active", date(2027, 1, 1)),
            R("PR-5", "Close", "Finished", date(2027, 1, 2)), R("PR-6", "Submit", "Aborted", date(2027, 1, 2)),
            R("PR-7", "Approve", "Active", None)]


def test_report_counts_active_only_and_uses_per_stage_thresholds():
    rep = report.build("Project Approval", rows(), ["Submit", "Finance Review", "Approve", "Close"],
                       {"default": 5, "Finance Review": 3}, date(2027, 1, 15))
    by = {line.stage: line for line in rep.lines}
    assert rep.total == 7 and rep.by_state == {"Active": 5, "Finished": 1, "Aborted": 1}
    assert (by["Submit"].active, by["Finance Review"].active, by["Approve"].active, by["Close"].active) == (1, 2, 2, 0)
    assert [r.code for r in rep.stuck] == ["PR-2", "PR-4"]       # 5 d > 3 (Finance); 14 d > 5 (Approve)
    assert by["Approve"].oldest == 14 and by["Finance Review"].average == 3.5


def test_report_keeps_unknown_stages_and_renders():
    rs = rows() + [report.Row("PR-8", "Legacy stage", "Active", date(2027, 1, 15))]
    rep = report.build("Project Approval", rs, ["Submit"], {"default": 5}, date(2027, 1, 15))
    assert [line.stage for line in rep.lines][:1] == ["Submit"] and "Legacy stage" in [l.stage for l in rep.lines]
    text = "\n".join(report.render(rep, {"default": 5}, date(2027, 1, 15)))
    assert text.startswith("Project Approval: 8 instances (1 aborted, 6 active, 1 finished)")
    assert "PR-4       Approve          since 2027-01-01 (14 d)" in text


def test_rows_from_api_uses_expanded_record_code_and_stage_names():
    raw = [{"_activestageid_value": "{AAAA}", "statecode": 0, "statuscode": 1, "activestagestartedon": "2027-01-10",
            "_bpf_x_value": "rec1", "bpf_x": {"mgl_requestcode": "PR-0001"}},
           {"_activestageid_value": "zzzz", "statecode": 0, "statuscode": 2, "_bpf_x_value": "rec2"}]
    out = report.rows_from_api(raw, {"aaaa": "Submit"}, "_bpf_x_value", "bpf_x", "mgl_requestcode")
    assert (out[0].code, out[0].stage, out[0].state) == ("PR-0001", "Submit", "Active")
    assert (out[1].code, out[1].stage, out[1].state, out[1].started) == ("rec2", "zzzz", "Finished", None)
