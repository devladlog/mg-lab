"""The KQL: every statement is parsed and semantically analysed by Microsoft's Kusto.Language (src/KqlCheck, .NET).
There is no Kusto engine in the container, so nothing here *runs* a query: the demo is the proof that results match the reference."""
import json
import re
import shutil
import subprocess

import pytest

import events
from conftest import KQL, SRC

DOTNET = shutil.which("dotnet")
needs_dotnet = pytest.mark.skipif(DOTNET is None, reason="dotnet not installed")


@pytest.fixture(scope="session")
def kqlcheck(tmp_path_factory):
    out = tmp_path_factory.mktemp("kqlcheck")
    r = subprocess.run([DOTNET, "build", str(SRC / "KqlCheck" / "KqlCheck.csproj"), "-c", "Release", "--artifacts-path", str(out), "-v", "q", "-nologo"],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    dll = out / "bin" / "KqlCheck" / "release" / "KqlCheck.dll"
    assert dll.exists()
    return lambda folder: subprocess.run([DOTNET, str(dll), str(folder)], capture_output=True, text=True, timeout=120)


@needs_dotnet
def test_all_statements_are_valid(kqlcheck):
    r = kqlcheck(KQL)
    assert r.returncode == 0, r.stdout
    assert "10 statements, 0 errors" in r.stdout


@needs_dotnet
def test_the_checker_really_fails_on_a_broken_command_and_on_a_broken_query(kqlcheck, tmp_path):
    (tmp_path / "queries").mkdir()
    schema = (KQL / "01-schema.kql").read_text(encoding="utf-8")
    (tmp_path / "01-schema.kql").write_text(schema.replace("policy retention", "policy retentio"), encoding="utf-8")
    (tmp_path / "queries" / "a.kql").write_text("TillEventsUnique\n| summarize x = sum(Amountt)\n", encoding="utf-8")
    r = kqlcheck(tmp_path)
    assert r.returncode == 1
    assert "Expected one of" in r.stdout and "Amountt" in r.stdout


@needs_dotnet
def test_a_good_copy_passes(kqlcheck, tmp_path):
    shutil.copytree(KQL, tmp_path / "k")
    assert kqlcheck(tmp_path / "k").returncode == 0


def _statements(text):
    return [b for b in re.split(r"\n\s*\n", text) if b.strip()]


def test_table_columns_and_mapping_equal_the_event_fields():
    schema = (KQL / "01-schema.kql").read_text(encoding="utf-8")
    cols = re.search(r"^\.create-merge table TillEventsRaw \((.+)\)$", schema, flags=re.M).group(1)
    pairs = [c.strip().split(":") for c in cols.split(",")]
    assert [n for n, _ in pairs] == events.FIELDS
    kinds = dict(pairs)
    assert kinds["EventTime"] == "datetime" and kinds["Quantity"] == "int" and kinds["Amount"] == "real" and kinds["Store"] == "string"
    mapping = json.loads(re.search(r"ingestion json mapping 'TillEventsRawMapping' '(.+)'$", schema, flags=re.M).group(1))
    assert [m["column"] for m in mapping] == events.FIELDS
    assert all(m["Properties"]["Path"] == "$." + m["column"] and m["datatype"] == kinds[m["column"]] for m in mapping)


def test_dedupe_view_follows_learn():
    schema = (KQL / "01-schema.kql").read_text(encoding="utf-8")
    assert "materialized-view with (lookback=6h) TillEventsUnique on table TillEventsRaw" in schema
    assert "summarize take_any(*) by EventId" in schema


def test_dashboard_queries_read_the_deduplicated_view_and_diagnostics_the_raw_table():
    for f in (KQL / "queries").glob("*.kql"):
        text = f.read_text(encoding="utf-8")
        raw = "TillEventsRaw" in text
        assert raw == (f.stem in ("duplicates", "late-arrivals")), f.name
        assert raw or "TillEventsUnique" in text


def test_every_query_file_is_one_statement_without_blank_lines():
    """KqlCheck (and the Kusto Explorer convention) split on blank lines: a query must not contain one."""
    for f in (KQL / "queries").glob("*.kql"):
        assert len(_statements(f.read_text(encoding="utf-8"))) == 1, f.name


def test_totals_check_uses_the_default_run_id():
    import inspect
    assert inspect.signature(events.build_plan).parameters["run_id"].default == "demo17"
    assert 'RunId == "demo17"' in (KQL / "queries" / "totals-check.kql").read_text(encoding="utf-8")
