"""The extension (TypeScript) and the episode 1 commit-msg hook (Python) must give the same verdicts.

Needs the compiled extension (cd src/mg-commit && npm run compile) and the episode 1 folder next to this one.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parent.parent
RULES_JS = EPISODE / "src" / "mg-commit" / "out" / "commitRules.js"
EP1_TOOLS = EPISODE.parent / "01-git-github-best-practices" / "src" / "kit" / "tools"

pytestmark = pytest.mark.skipif(
    not RULES_JS.exists() or not EP1_TOOLS.exists() or not shutil.which("node"),
    reason="needs node, the compiled extension and the episode 1 kit",
)

CORPUS = [
    "feat: add paging", "fix(api): handle empty file", "feat(api)!: drop v1", "docs(readme): explain hooks",
    "refactor(orders/export): split writer", "fix: trim\n\nbody", "fix: trim\nbody", "Updated stuff",
    "feat:add paging", "Feat: add paging", "feature: add paging", "fix: done.", "", "   \n\n",
    "Merge branch 'main'", 'Revert "feat: x"', "fixup! feat: x", "squash! fix: y", "amend! fix: y",
    "feat: " + "x" * 66, "feat: " + "x" * 67, "chore(deps): bump pytest", "ci: pin actions",
    "# comment only", "# c\nfeat: ok\n\n# ------------------------ >8 ------------------------\nmore",
    "fix(UI): upper-case scope", "fix(): empty scope", "perf!: faster", "test(e2e): add crlf case",
    "fix: windows\r\n\r\nbody\r\n",
]


def test_typescript_and_python_rules_agree():
    sys.path.insert(0, str(EP1_TOOLS))
    from repo_guard.commit_rules import check_message  # episode 1

    script = (
        f"const r = require({json.dumps(str(RULES_JS))});"
        "const msgs = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(msgs.map(m => r.checkMessage(m).ok)));"
    )
    out = subprocess.run(["node", "-e", script], input=json.dumps(CORPUS), capture_output=True, text=True, check=True)
    ts_verdicts = json.loads(out.stdout)
    py_verdicts = [check_message(m).ok for m in CORPUS]
    mismatches = [(m, t, p) for m, t, p in zip(CORPUS, ts_verdicts, py_verdicts) if t != p]
    assert not mismatches, mismatches
    assert any(py_verdicts) and not all(py_verdicts)
