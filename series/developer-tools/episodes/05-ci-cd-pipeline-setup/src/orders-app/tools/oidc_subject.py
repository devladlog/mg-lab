#!/usr/bin/env python3
"""Print the exact `sub` claim a GitHub Actions job will present to Microsoft Entra ID.

    gh api repos/<owner>/<repo> | python3 tools/oidc_subject.py --environment production
    python3 tools/oidc_subject.py --repo-json repo.json --environment production --format legacy

The federated identity credential must match it exactly (case-sensitive, no wildcards). Two formats exist:
  legacy     repo:<owner>/<repo>:environment:<env>
  immutable  repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<env>
GitHub uses the immutable format for repositories created (or renamed/transferred) after 15 July 2026 and for
repositories that opted in. `--format auto` decides from `created_at`, which can't see renames, transfers or
opt-ins: if Azure answers AADSTS700213, the error message contains the subject GitHub actually presented.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

IMMUTABLE_SINCE = datetime(2026, 7, 15, tzinfo=timezone.utc)


def subject(repo: dict, environment: str | None = None, ref: str | None = None, fmt: str = "auto") -> str:
    if (environment is None) == (ref is None):
        raise ValueError("give exactly one of environment or ref")
    owner, name = repo["owner"]["login"], repo["name"]
    if fmt == "auto":
        created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
        fmt = "immutable" if created > IMMUTABLE_SINCE else "legacy"
    if fmt == "immutable":
        prefix = f"repo:{owner}@{repo['owner']['id']}/{name}@{repo['id']}"
    elif fmt == "legacy":
        prefix = f"repo:{owner}/{name}"
    else:
        raise ValueError(f"unknown format {fmt!r}")
    return f"{prefix}:environment:{environment}" if environment else f"{prefix}:ref:{ref}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo-json", help="output of `gh api repos/<owner>/<repo>` (default: stdin)")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--environment", help="job uses `environment: <name>`")
    target.add_argument("--ref", help="job has no environment, e.g. refs/heads/main")
    p.add_argument("--format", choices=["auto", "immutable", "legacy"], default="auto")
    a = p.parse_args(argv)
    raw = open(a.repo_json, encoding="utf-8").read() if a.repo_json else sys.stdin.read()
    print(subject(json.loads(raw), a.environment, a.ref, a.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
