import json
import subprocess
import sys

from conftest import CLEAN, RAW, SRC


def run(*args):
    return subprocess.run([sys.executable, "-m", "pmkit", *args], cwd=SRC, capture_output=True, text=True)


def test_generate_writes_the_committed_sample(tmp_path):
    out = tmp_path / "log.csv"
    assert run("generate", "--out", str(out)).returncode == 0
    assert out.read_bytes() == CLEAN.read_bytes()


def test_doctor_exit_codes_and_mapping_hint():
    ok = run("doctor", str(CLEAN))
    assert ok.returncode == 0 and "CaseId = Case ID" in ok.stdout and "Amount = Financial per case (first event)" in ok.stdout
    bad = run("doctor", str(RAW))
    assert bad.returncode == 1 and "PM002" in bad.stdout and "PM003" in bad.stdout


def test_clean_then_doctor_then_analyze(tmp_path):
    out = tmp_path / "fixed.csv"
    r = run("clean", str(RAW), "--out", str(out))
    assert r.returncode == 0 and "dropped_duplicates: 12" in r.stdout and "wrote 1781 rows" in r.stdout
    assert run("doctor", str(out)).returncode == 0
    a = run("analyze", str(out), "--json")
    assert json.loads(a.stdout)["variants"] == 17


def test_analyze_text_report():
    r = run("analyze", str(CLEAN), "--before", "Manager review", "Place order")
    assert r.returncode == 0
    assert "cases 300  events 1781  activities 9  variants 17" in r.stdout
    assert "rework cases 28.0 %" in r.stdout
    assert "Place order before Manager review: 8 case(s)" in r.stdout
