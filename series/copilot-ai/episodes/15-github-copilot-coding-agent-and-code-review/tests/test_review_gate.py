import json
import subprocess

from agent_ready import review_gate as rg

PR = {"user": {"login": "Copilot"}, "draft": False, "state": "open", "merged": False, "head": {"sha": "0" * 40}}


def rev(login, state, at):
    return {"user": {"login": login}, "state": state, "submitted_at": at}


GREEN = [{"name": "ci", "status": "completed", "conclusion": "success"}]


def status(verdict, name):
    return next(c.status for c in verdict.checks if c.name == name)


def test_ready_when_human_approved_and_workflows_green():
    v = rg.evaluate(PR, [rev("copilot-pull-request-reviewer[bot]", "COMMENTED", "1"), rev("sam.demo", "APPROVED", "2")], GREEN, "alex.demo")
    assert v.ready, v.render()


def test_requester_cannot_approve_their_own_agent_pr():
    v = rg.evaluate(PR, [rev("alex.demo", "APPROVED", "1")], GREEN, "alex.demo")
    assert status(v, "human approval") == "wait" and "own approval" in v.render() and not v.ready


def test_copilot_review_never_counts_as_approval():
    v = rg.evaluate(PR, [rev("copilot-pull-request-reviewer[bot]", "APPROVED", "1")], GREEN, "alex.demo")
    assert status(v, "human approval") == "wait"


def test_latest_review_per_person_wins():
    v = rg.evaluate(PR, [rev("sam.demo", "CHANGES_REQUESTED", "1"), rev("sam.demo", "APPROVED", "2")], GREEN, "alex.demo")
    assert status(v, "human approval") == "ok"
    v2 = rg.evaluate(PR, [rev("sam.demo", "APPROVED", "1"), rev("sam.demo", "CHANGES_REQUESTED", "2")], GREEN, "alex.demo")
    assert status(v2, "changes requested") == "block"


def test_pending_reviews_are_ignored():
    v = rg.evaluate(PR, [rev("sam.demo", "PENDING", "1")], GREEN, "alex.demo")
    assert status(v, "human approval") == "wait"


def test_draft_blocks_readiness():
    v = rg.evaluate({**PR, "draft": True}, [rev("sam.demo", "APPROVED", "1")], GREEN, "alex.demo")
    assert status(v, "draft") == "wait" and not v.ready


def test_no_runs_means_approve_and_run_workflows():
    v = rg.evaluate(PR, [rev("sam.demo", "APPROVED", "1")], [], "alex.demo")
    assert status(v, "workflows") == "wait" and "Approve and run workflows" in v.render()


def test_action_required_run_waits_failed_run_blocks_running_waits():
    ap = [{"name": "ci", "status": "completed", "conclusion": "action_required"}]
    assert status(rg.evaluate(PR, [], ap, "a"), "workflows") == "wait"
    bad = [{"name": "ci", "status": "completed", "conclusion": "failure"}]
    assert status(rg.evaluate(PR, [], bad, "a"), "workflows") == "block"
    going = [{"name": "ci", "status": "in_progress", "conclusion": None}]
    assert status(rg.evaluate(PR, [], going, "a"), "workflows") == "wait"


def test_closed_and_merged():
    assert status(rg.evaluate({**PR, "state": "closed"}, [], [], "a"), "state") == "block"
    assert rg.evaluate({**PR, "merged": True, "state": "closed"}, [], [], "a").ready


def test_human_authored_pr_is_noted():
    v = rg.evaluate({**PR, "user": {"login": "sam.demo"}}, [], GREEN, "a")
    assert status(v, "author") == "wait"


def test_fetch_reads_three_endpoints_with_gh():
    calls = []

    def runner(args, capture_output, text, check):
        calls.append(args[-1])
        body = {"/repos/a/b/pulls/5": PR}.get(args[-1])
        if body is None and "reviews" in args[-1]:
            body = [rev("sam.demo", "APPROVED", "1")]
        if body is None:
            body = {"workflow_runs": GREEN}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body), stderr="")

    pr, reviews, runs = rg.fetch("a/b", 5, runner)
    assert len(calls) == 3 and calls[2].startswith(f"/repos/a/b/actions/runs?head_sha={'0'*40}")
    assert reviews[0]["state"] == "APPROVED" and runs == GREEN
