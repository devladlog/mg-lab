"""Build (once) and run tools/TsqlParse: Microsoft's T-SQL parser (ScriptDom) as a JSON-printing CLI.

The build output goes to the system temp folder (dotnet --artifacts-path), never into the repo.
Tests that need it are skipped when the .NET SDK isn't installed.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "TsqlParse"


def available() -> bool:
    return shutil.which("dotnet") is not None


@lru_cache(maxsize=1)
def tool_dll() -> Path:
    sources = b"".join(p.read_bytes() for p in sorted(TOOL.glob("*")) if p.is_file())
    tag = hashlib.sha256(sources).hexdigest()[:12]
    artifacts = Path(tempfile.gettempdir()) / f"{ROOT.name}-tsqlparse-{tag}"
    dll = artifacts / "bin" / "TsqlParse" / "release" / "TsqlParse.dll"
    if not dll.exists():
        subprocess.run(["dotnet", "build", str(TOOL / "TsqlParse.csproj"), "-c", "Release", "-m:1", "-nologo",
                        "-v", "q", "--artifacts-path", str(artifacts)], check=True, capture_output=True, text=True)
    return dll


def parse(*paths: Path) -> tuple[int, list[dict]]:
    """(exit code, one JSON object per file)."""
    proc = subprocess.run(["dotnet", str(tool_dll()), *map(str, paths)], capture_output=True, text=True)
    return proc.returncode, json.loads(proc.stdout)


@lru_cache(maxsize=1)
def parse_all_sql() -> dict[str, dict]:
    code, files = parse(*sorted((ROOT / "src" / "sql").glob("*.sql")))
    return {f["file"]: f for f in files}


def modules() -> dict[str, dict]:
    return {m["name"]: m for f in parse_all_sql().values() for m in f["modules"]}
