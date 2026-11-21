#!/usr/bin/env python3
"""Write requirements-test.txt for every episode that has Python tests.

The list is derived from the third-party imports in the episode's own .py files (src, tests, tools),
merged with any requirements*.txt the episode already has, plus pytest. Names are unpinned on purpose:
the recording laptop may run an older Python than the build container, so pip picks versions that fit.

Usage: python3 series/tools/make_test_requirements.py [episode folders...]   (default: all)
"""
from __future__ import annotations

import ast
import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".venv", "venv", "bin", "obj", "__pycache__", ".git", "reference", "legacy"}
# import name -> pip name, for packages the build container may not have installed globally
KNOWN = {
    "yaml": "PyYAML", "sklearn": "scikit-learn", "PIL": "pillow", "cv2": "opencv-python-headless",
    "dateutil": "python-dateutil", "docx": "python-docx", "pptx": "python-pptx", "bs4": "beautifulsoup4",
    "jwt": "PyJWT", "dotenv": "python-dotenv", "msal": "msal", "kusto": "azure-kusto-data", "sqlglot": "sqlglot",
    "duckdb": "duckdb", "pyspark": "pyspark", "delta": "delta-spark", "mlflow": "mlflow", "tiktoken": "tiktoken",
    "openai": "openai", "anthropic": "anthropic", "mcp": "mcp", "httpx": "httpx", "requests": "requests",
    "jsonschema": "jsonschema", "pandas": "pandas", "numpy": "numpy", "pyarrow": "pyarrow", "lxml": "lxml",
    "pydantic": "pydantic", "fastapi": "fastapi", "uvicorn": "uvicorn", "flask": "flask", "jinja2": "Jinja2",
    "pymssql": "pymssql", "pyodbc": "pyodbc", "azureml": "azureml-core", "google": "google-genai",
    "piexif": "piexif", "markdown": "Markdown", "tabulate": "tabulate", "rich": "rich", "click": "click",
    "typer": "typer", "scipy": "scipy", "matplotlib": "matplotlib", "psutil": "psutil", "pytest": "pytest",
}
AZURE_NS = re.compile(r"^azure\.([a-z0-9_]+(?:\.[a-z0-9_]+)?)")


def episodes(args: list[str]) -> list[Path]:
    if args:
        return [Path(a).resolve() for a in args]
    return sorted(p.parent for p in ROOT.glob("series/*/episodes/*/script.yaml"))


def py_files(ep: Path):
    for p in ep.rglob("*.py"):
        if not SKIP_DIRS.intersection(p.relative_to(ep).parts):
            yield p


def local_names(ep: Path) -> set[str]:
    names = set()
    for p in py_files(ep):
        names.add(p.stem)
        for parent in p.relative_to(ep).parents:
            if parent.name:
                names.add(parent.name)
    return names


def imports(ep: Path) -> set[str]:
    found: set[str] = set()
    for p in py_files(ep):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module)
    return found


def pip_name(mod: str, dists: dict[str, list[str]]) -> str | None:
    top = mod.split(".")[0]
    if top == "azure":
        m = AZURE_NS.match(mod)
        if m:
            parts = m.group(1).split(".")
            # azure.identity -> azure-identity; azure.ai.projects -> azure-ai-projects; azure.storage.blob -> azure-storage-blob
            if parts[0] in {"ai", "storage", "mgmt", "monitor", "search", "eventhub", "keyvault", "data", "cosmos", "core", "iot", "servicebus", "communication"} and len(parts) > 1:
                cand = f"azure-{parts[0]}-{parts[1]}".replace("_", "-")
            else:
                cand = f"azure-{parts[0]}".replace("_", "-")
            if cand == "azure-core-pipeline":
                cand = "azure-core"
            if cand == "azure-iot-device":
                return "azure-iot-device"
            return cand
        return None
    if top == "google":
        return "google-genai" if mod.startswith("google.genai") else None
    if top in dists:
        return dists[top][0]
    return KNOWN.get(top)


def existing_reqs(ep: Path) -> list[str]:
    out = []
    for f in ep.rglob("requirements*.txt"):
        if SKIP_DIRS.intersection(f.relative_to(ep).parts) or f.name == "requirements-test.txt":
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith(("-", "--")):
                out.append(line)
    return out


def main(argv: list[str]) -> int:
    dists = md.packages_distributions()
    stdlib = set(sys.stdlib_module_names) | {"__future__", "_pytest", "pkg_resources", "setuptools", "distutils"}
    written = 0
    for ep in episodes(argv):
        if not any(p.name.startswith("test_") or p.name == "conftest.py" for p in py_files(ep)):
            continue
        local = local_names(ep)
        names: dict[str, str] = {}
        for req in existing_reqs(ep):
            base = re.split(r"[<>=!~\[; ]", req, maxsplit=1)[0]
            names[base.lower()] = base
        for mod in sorted(imports(ep)):
            top = mod.split(".")[0]
            if top in stdlib or top in local or top.startswith("_"):
                continue
            name = pip_name(mod, dists)
            if name:
                names.setdefault(name.lower(), name)
        names.setdefault("pytest", "pytest")
        lines = ["# Generated by series/tools/make_test_requirements.py: what the tests import (unpinned).",
                 "# pip install -r requirements-test.txt   then   python -m pytest -q tests"]
        lines += sorted(names.values(), key=str.lower)
        (ep / "requirements-test.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    print(f"{written} requirements-test.txt written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
