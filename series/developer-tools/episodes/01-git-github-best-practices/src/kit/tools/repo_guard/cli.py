"""Entry points for the Git hooks and for CI.

  python3 tools/repo_guard/cli.py title "feat(api): add paging"   # CI: PR title check
  python3 tools/repo_guard/cli.py scan-tree                       # CI: secrets in tracked files
  .githooks/commit-msg  -> commit_msg_main([path])
  .githooks/pre-commit  -> pre_commit_main()
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `repo_guard` importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_guard.commit_rules import ALLOWED_TYPES, check_message  # noqa: E402
from repo_guard.staged_checks import check_branch, check_staged, scan_tree  # noqa: E402

HINT = (
    "Examples:\n"
    "  feat(api): add paging to the orders endpoint\n"
    "  fix: handle empty export files\n"
    "  docs(readme): explain the hook setup\n"
    f"Types: {', '.join(ALLOWED_TYPES)}. Add ! before the colon for a breaking change."
)


def _fail(title: str, problems: list) -> int:
    print(f"✗ {title}", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1


def commit_msg_main(argv: list[str]) -> int:
    message = Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    result = check_message(message)
    if result.ok:
        return 0
    _fail("commit message rejected", result.errors)
    print(HINT, file=sys.stderr)
    print("Your message is kept in .git/COMMIT_EDITMSG.", file=sys.stderr)
    return 1


def pre_commit_main() -> int:
    problems = [*check_branch(), *map(str, check_staged())]
    if problems:
        return _fail("commit blocked", problems)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "title":
        result = check_message(argv[1])
        if result.ok:
            print(f"✓ PR title ok ({result.type}{' BREAKING' if result.breaking else ''})")
            return 0
        _fail("PR title is not a Conventional Commit (squash merge uses it as the commit message)", result.errors)
        print(HINT, file=sys.stderr)
        return 1
    if argv == ["scan-tree"]:
        findings = scan_tree()
        if findings:
            return _fail(f"{len(findings)} possible secret(s) in tracked files", findings)
        print("✓ no secrets found in tracked files")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
