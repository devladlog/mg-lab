"""Runs asa/coldroom-telemetry.asaql on the real Stream Analytics local runtime (azure-streamanalytics-cicd, needs dotnet).

Local runs use static input files, so the time policies (late arrival, out of order) are NOT exercised here
(the runtime says so: "Time policy ... is not supported for local static input file").
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from asa_reference import expected_aggregates, expected_alerts
from conftest import ASA, CASES
from iotlab.telemetry import DEFAULT_ROOMS, make_reading

CASE_NAMES = ["steady", "warm-room", "malformed"]


def write_lines(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


def make_test_config(script: Path, cases: list[dict]) -> dict:
    return {"Script": str(script), "TestCases": cases}


def case_entry(name: str, input_file: Path, expected: dict[str, Path], ignore: tuple[str, ...] = ()) -> dict:
    return {
        "Name": name,
        "Inputs": [{"InputAlias": "telemetry", "Type": "Data Stream", "Format": "Json", "FilePath": str(input_file), "ScriptType": "InputMock"}],
        "ExpectedOutputs": [{"OutputAlias": alias, "FilePath": str(path), "IgnoreFields": list(ignore), "Required": True}
                            for alias, path in expected.items()],
    }


def run_cli(cli: Path, project: Path, config: dict, work: Path) -> tuple[int, dict]:
    cfg = work / "testConfig.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    out = work / "out"
    done = subprocess.run([str(cli), "test", "--project", str(project / "asaproj.json"), "--testConfigPath", str(cfg), "--outputPath", str(out)],
                          capture_output=True, text=True, timeout=600)
    summary = json.loads((out / "testResultSummary.json").read_text(encoding="utf-8")) if (out / "testResultSummary.json").exists() else {}
    return done.returncode, summary


@pytest.fixture(scope="module")
def committed_cases(asa_cli, tmp_path_factory):
    entries = []
    for name in CASE_NAMES:
        folder = CASES / name
        expected = {"aggregates": folder / "aggregates.json"}
        if (folder / "alerts.json").exists():
            expected["alerts"] = folder / "alerts.json"
        entries.append(case_entry(name, folder / "input.json", expected))
    work = tmp_path_factory.mktemp("asa-cases")
    code, summary = run_cli(asa_cli, ASA, make_test_config(ASA / "coldroom-telemetry.asaql", entries), work)
    return code, {r["Name"]: r for r in summary.get("Results", [])}


@pytest.mark.parametrize("name", CASE_NAMES)
def test_query_matches_the_expected_output_of_each_case(committed_cases, name):
    code, results = committed_cases
    result = results[name]
    assert result["Status"] == 0, result
    assert not result["OutputNotEqual"] and not result["OutputMissing"] and not result["OutputUnexpected"]
    assert any(m["OutputAlias"] == "aggregates" for m in result["OutputMatched"])


def test_warm_room_case_really_checks_the_alert_output(committed_cases):
    _, results = committed_cases
    assert {m["OutputAlias"] for m in results["warm-room"]["OutputMatched"]} == {"aggregates", "alerts"}


def test_cases_on_disk_equal_the_independent_reference_model():
    for name in CASE_NAMES:
        events = json.loads((CASES / name / "input.json").read_text())
        got = [json.loads(line) for line in (CASES / name / "aggregates.json").read_text().splitlines()]
        assert got == expected_aggregates(events)
        alerts_file = CASES / name / "alerts.json"
        want = expected_alerts(events)
        assert (not want) if not alerts_file.exists() else ([json.loads(l) for l in alerts_file.read_text().splitlines()] == want)


@pytest.fixture(scope="module")
def mutated_project(tmp_path_factory):
    copy = tmp_path_factory.mktemp("mutant") / "asa"
    shutil.copytree(ASA, copy)
    query = copy / "coldroom-telemetry.asaql"
    text = query.read_text(encoding="utf-8")
    assert "AVG(temperatureC) > 8.0" in text
    query.write_text(text.replace("AVG(temperatureC) > 8.0", "AVG(temperatureC) > 4.0"), encoding="utf-8")
    return copy


def test_the_harness_catches_a_changed_threshold(asa_cli, mutated_project, tmp_path):
    folder = CASES / "warm-room"
    entry = case_entry("warm-room-mutant", folder / "input.json", {"aggregates": folder / "aggregates.json", "alerts": folder / "alerts.json"})
    code, summary = run_cli(asa_cli, mutated_project, make_test_config(mutated_project / "coldroom-telemetry.asaql", [entry]), tmp_path)
    assert code != 0 and summary["Failed"] == 1
    assert summary["Results"][0]["OutputNotEqual"][0]["OutputAlias"] == "alerts"


def test_simulator_door_open_scenario_raises_the_alert_for_coldroom_02_only(asa_cli, tmp_path):
    """The simulator's payload goes through the real query: field names and the threshold agree."""
    rng = random.Random(18)
    start = datetime(2026, 11, 20, 10, 0, 5, tzinfo=timezone.utc)  # in the past: the local runtime clamps future events
    events = []
    for tick in range(120):  # 10 minutes at 5 s
        moment = start + timedelta(seconds=5 * tick)
        events += [make_reading(room, moment, tick, "door-open", rng) for room in DEFAULT_ROOMS]
    assert expected_alerts(events), "scenario is too mild to raise an alert"
    assert {a["deviceId"] for a in expected_alerts(events)} == {"coldroom-02"}

    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(events), encoding="utf-8")
    aggregates, alerts = tmp_path / "aggregates.json", tmp_path / "alerts.json"
    write_lines(aggregates, expected_aggregates(events))
    write_lines(alerts, expected_alerts(events))
    # Random floats sum in a different order in the engine (Learn: "slight differences in the produced values"), so the
    # exact comparison skips avgTempC and a second check compares it with a tolerance.
    entry = case_entry("simulator-door-open", input_file, {"aggregates": aggregates, "alerts": alerts}, ignore=("avgTempC",))
    code, summary = run_cli(asa_cli, ASA, make_test_config(ASA / "coldroom-telemetry.asaql", [entry]), tmp_path)
    assert code == 0 and summary["Passed"] == 1, summary
    for alias, want in (("aggregates", expected_aggregates(events)), ("alerts", expected_alerts(events))):
        got = [json.loads(line) for line in (tmp_path / "out" / "simulator-door-open" / f"{alias}.json").read_text().splitlines()]
        key = lambda r: (r["windowEnd"], r["deviceId"])
        got, want = sorted(got, key=key), sorted(want, key=key)
        assert [key(r) for r in got] == [key(r) for r in want]
        assert [r["avgTempC"] for r in got] == pytest.approx([r["avgTempC"] for r in want], abs=1e-9)


def test_project_builds_to_an_arm_template(asa_cli, tmp_path):
    """`build --v2` does the keyword and syntax check of the query and the job files and emits the deployable template."""
    done = subprocess.run([str(asa_cli), "build", "--v2", "--project", str(ASA / "asaproj.json"), "--outputPath", str(tmp_path)],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    template = json.loads((tmp_path / "coldroom-telemetry.JobTemplate.json").read_text(encoding="utf-8-sig"))
    job = next(r for r in template["resources"] if r["type"].lower() == "microsoft.streamanalytics/streamingjobs")
    text = json.dumps(job)
    assert job["identity"]["type"] == "SystemAssigned" and "TumblingWindow" in text
    params = json.loads((tmp_path / "coldroom-telemetry.JobTemplate.parameters.json").read_text(encoding="utf-8-sig"))
    assert all(v.get("value") is None for k, v in params["parameters"].items() if k.endswith("Key"))  # credentials default to null
    assert [v["value"]["DataSource"]["AuthenticationMode"] for k, v in params["parameters"].items() if k.startswith("Outputs_") and isinstance(v.get("value"), dict)] == ["Msi", "Msi"]


def test_localrun_with_the_projects_own_input_mock_writes_the_alert(asa_cli, tmp_path):
    """`azure-streamanalytics-cicd localrun --project asa/asaproj.json` is the command the README tells you to run."""
    out = tmp_path / "lr"
    done = subprocess.run([str(asa_cli), "localrun", "--project", str(ASA / "asaproj.json"), "--outputPath", str(out)],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stdout + done.stderr
    read = lambda path: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert read(out / "alerts.json") == read(CASES / "warm-room" / "alerts.json")
    assert read(out / "alerts.json")
