import json
import subprocess

import pytest

from agent_ready import assign


def test_assignment_body_matches_the_documented_shape():
    req = assign.assignment_request("contoso-lab/bikes", 7, "main", "Run the tests", "")
    assert req.method == "POST" and req.path == "/repos/contoso-lab/bikes/issues/7/assignees"
    assert req.body == {
        "assignees": ["copilot-swe-agent[bot]"],
        "agent_assignment": {"target_repo": "contoso-lab/bikes", "base_branch": "main", "custom_instructions": "Run the tests", "custom_agent": "", "model": ""},
    }
    assert req.headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_gh_args_pass_headers_and_read_body_from_stdin():
    args = assign.assignment_request("a/b", 1).gh_args()
    assert args[:5] == ["gh", "api", "--method", "POST", "/repos/a/b/issues/1/assignees"]
    assert "Accept: application/vnd.github+json" in args and args[-2:] == ["--input", "-"]


@pytest.mark.parametrize("repo,issue,branch", [("nobody", 1, "main"), ("a/b", 0, "main"), ("a/b", 1, ""), ("a/b", 1, "feat..x"), ("a/b", 1, "has space")])
def test_bad_input_is_rejected(repo, issue, branch):
    with pytest.raises(ValueError):
        assign.assignment_request(repo, issue, branch)


def test_review_request():
    req = assign.review_request("a/b", 3)
    assert req.path == "/repos/a/b/pulls/3/requested_reviewers"
    assert req.body == {"reviewers": ["copilot-pull-request-reviewer[bot]"]}


def test_send_uses_runner_and_parses_json():
    seen = {}

    def runner(args, input, capture_output, text, check):
        seen.update(args=args, input=input)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"number": 7, "state": "open"}), stderr="")

    out = assign.send(assign.assignment_request("a/b", 7), runner)
    assert out["number"] == 7 and json.loads(seen["input"])["assignees"] == ["copilot-swe-agent[bot]"]


def test_send_raises_with_the_cli_message():
    def runner(args, **kw):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="gh: Not Found (HTTP 404)")

    with pytest.raises(RuntimeError, match="Not Found"):
        assign.send(assign.review_request("a/b", 1), runner)
