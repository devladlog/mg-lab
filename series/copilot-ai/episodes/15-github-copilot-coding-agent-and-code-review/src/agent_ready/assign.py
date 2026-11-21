"""Build (and optionally send) the GitHub REST calls that hand work to Copilot.

Docs (docs.github.com, "Use cloud agent via the API", read 21 Nov 2026): the issues API for this is in public preview
and may change. Assign with POST /repos/OWNER/REPO/issues/N/assignees and the assignee `copilot-swe-agent[bot]`; the
optional `agent_assignment` object has target_repo, base_branch, custom_instructions, custom_agent and model. Only
user-to-server tokens work (personal access token, OAuth app token, GitHub App user-to-server token), not an
installation token. A review is requested by adding `copilot-pull-request-reviewer[bot]` as a reviewer.

The default is a dry run that only prints the request. `--execute` calls `gh api`, which uses the token you signed in with.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable

AGENT_ASSIGNEE = "copilot-swe-agent[bot]"
REVIEWER = "copilot-pull-request-reviewer[bot]"
API_VERSION = "2022-11-28"
_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_BAD = re.compile(r"[\s~^:?*\[\\]|\.\.|^/|/$|\.lock$|@\{")


@dataclass
class Request:
    method: str
    path: str
    body: dict
    headers: dict = field(default_factory=lambda: {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION})

    def gh_args(self) -> list[str]:
        args = ["gh", "api", "--method", self.method, self.path]
        for k, v in self.headers.items():
            args += ["-H", f"{k}: {v}"]
        return args + ["--input", "-"]

    def describe(self) -> str:
        return f"{self.method} {self.path}\n{json.dumps(self.body, indent=2)}"


def _check_slug(repo: str) -> None:
    if not _SLUG.match(repo):
        raise ValueError(f"repository must look like OWNER/REPO, got {repo!r}")


def assignment_request(repo: str, issue: int, base_branch: str = "main", custom_instructions: str = "", model: str = "", custom_agent: str = "") -> Request:
    _check_slug(repo)
    if not isinstance(issue, int) or issue < 1:
        raise ValueError("issue number must be a positive integer")
    if not base_branch or _BRANCH_BAD.search(base_branch):
        raise ValueError(f"not a usable branch name: {base_branch!r}")
    body = {
        "assignees": [AGENT_ASSIGNEE],
        "agent_assignment": {
            "target_repo": repo,
            "base_branch": base_branch,
            "custom_instructions": custom_instructions,
            "custom_agent": custom_agent,
            "model": model,
        },
    }
    return Request("POST", f"/repos/{repo}/issues/{issue}/assignees", body)


def review_request(repo: str, pull: int) -> Request:
    _check_slug(repo)
    if not isinstance(pull, int) or pull < 1:
        raise ValueError("pull request number must be a positive integer")
    return Request("POST", f"/repos/{repo}/pulls/{pull}/requested_reviewers", {"reviewers": [REVIEWER]})


def send(req: Request, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    """Send through the GitHub CLI. Raises RuntimeError with the CLI's message on failure."""
    proc = runner(req.gh_args(), input=json.dumps(req.body), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or f"gh api exited with {proc.returncode}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}
