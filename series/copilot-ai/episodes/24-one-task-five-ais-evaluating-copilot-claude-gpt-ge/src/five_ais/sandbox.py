"""Run model-written Python against our tests, with layers of caution. THIS IS NOT A SECURITY BOUNDARY.

Layers: (1) opt-in only (`--allow-code-exec`), (2) an AST allow-list refuses imports outside a short list and calls to
open/eval/exec/compile/__import__/getattr-style escapes, (3) a separate interpreter in isolated mode (-I) with an empty
environment, a temp working directory and a timeout, (4) POSIX only: CPU and memory limits. For real isolation run the
whole harness in a throwaway VM.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap

ALLOWED_IMPORTS = {"datetime", "math", "re", "json", "decimal", "fractions", "collections", "itertools", "functools",
                   "typing", "string", "calendar", "dataclasses", "operator", "statistics"}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr"}


def extract_code(answer: str) -> str:
    """First fenced code block (```python ... ```), else the whole answer."""
    import re
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", answer, re.S | re.I)
    return (m.group(1) if m else answer).strip()


def vet(code: str) -> str | None:
    """Return a reason to refuse, or None if the code passes the allow-list."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"syntax error: {e.msg} (line {e.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    return f"import of {a.name} is not allowed"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                return f"import from {node.module} is not allowed"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            return f"call to {node.func.id}() is not allowed"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__") \
                and node.attr not in ("__name__", "__doc__", "__init__", "__eq__", "__lt__", "__repr__", "__str__"):
            return f"dunder attribute {node.attr} is not allowed"
    return None


_RUNNER = """
import json, sys
ns = {}
exec(compile(open(sys.argv[1], encoding="utf-8").read(), "model_code", "exec"), ns)
cases = json.loads(open(sys.argv[2], encoding="utf-8").read())
out = []
for c in cases:
    try:
        got = eval(c["call"], ns)
        out.append({"call": c["call"], "ok": got == c["expect"], "got": repr(got)[:80]})
    except Exception as e:
        out.append({"call": c["call"], "ok": False, "got": type(e).__name__ + ": " + str(e)[:60]})
print(json.dumps(out))
"""


def _limits():  # pragma: no cover - runs in the child on POSIX only
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 ** 2, 512 * 1024 ** 2))


def _env() -> dict:
    env = {"PYTHONIOENCODING": "utf-8"}
    if "SYSTEMROOT" in os.environ:     # Windows needs it to start Python at all
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def run_tests(code: str, cases: list[dict], timeout: float = 8.0) -> list[dict]:
    """cases: [{"call": "f(1, 2)", "expect": 3}] (call text comes from OUR task file, results from the model's code).
    Returns one {call, ok, got} per case, or a single failed entry with the refusal/timeout reason."""
    reason = vet(code)
    if reason:
        return [{"call": "(all)", "ok": False, "got": f"refused: {reason}"}]
    with tempfile.TemporaryDirectory(prefix="five_ais_") as d:
        for name, content in (("model_code.py", code), ("cases.json", json.dumps(cases)),
                              ("runner.py", textwrap.dedent(_RUNNER))):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(content)
        kw = {"preexec_fn": _limits} if os.name == "posix" else {}
        try:
            p = subprocess.run([sys.executable, "-I", os.path.join(d, "runner.py"), os.path.join(d, "model_code.py"),
                                os.path.join(d, "cases.json")], capture_output=True, text=True, timeout=timeout, cwd=d,
                               env=_env(), **kw)
        except subprocess.TimeoutExpired:
            return [{"call": "(all)", "ok": False, "got": f"timeout after {timeout}s"}]
        if p.returncode != 0:
            return [{"call": "(all)", "ok": False, "got": "crashed: " + (p.stderr.strip().splitlines() or ["?"])[-1][:120]}]
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return [{"call": "(all)", "ok": False, "got": "no result printed"}]
