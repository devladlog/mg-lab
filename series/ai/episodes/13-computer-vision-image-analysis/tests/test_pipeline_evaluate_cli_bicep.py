import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Scripted, analysis, ROOT
from photoscan import evaluate as ev
from photoscan import samples
from photoscan.cli import main
from photoscan.pipeline import Paced, process, write

CASES = ROOT / "data" / "cases.json"
RAW = samples.generate()


def test_process_end_to_end_and_original_never_returned_in_outputs():
    a = analysis(lines=[("CON-48213", 0.97)], people=[((100, 100, 200, 300), 0.9)], crops=[(1.0, (0, 0, 600, 600))])
    r = process(RAW["label-clean"], Scripted(a), "t1")
    assert r.decision == "attach-then-review" and r.tags[0].tag == "CON-48213"
    assert len(r.blurred) == 1 and r.redacted_png != r.prepared_png and r.thumb_png
    s = write(r, Path("/tmp/photoscan-test-out"))
    assert s["people_blurred"] == 1 and "asset_tags" in s
    shutil.rmtree("/tmp/photoscan-test-out")


def test_the_service_gets_the_prepared_bytes_not_the_original():
    be = Scripted(analysis())
    process(RAW["label-phone-rotated"], be, "t2")
    assert be.seen[0] != RAW["label-phone-rotated"] and b"ContosoPhone" not in be.seen[0]


def test_rejected_image_never_reaches_the_service():
    be = Scripted()
    r = process(b"junk", be, "bad")
    assert r.decision == "manual-review" and "not a readable image" in r.error and be.seen == []


def test_backend_failure_goes_to_a_person_and_does_not_raise():
    r = process(RAW["label-clean"], Scripted(RuntimeError("429")), "x")
    assert r.decision == "manual-review" and "analysis failed" in r.error and r.redacted_png is None


def test_summary_json_has_no_pixels_and_no_ocr_text(tmp_path):
    a = analysis(lines=[("Aaron Buston", 0.9), ("CON-48213", 0.97)])
    r = process(RAW["label-clean"], Scripted(a), "t3")
    s = write(r, tmp_path)
    blob = json.dumps(s)
    assert "Aaron" not in blob and "CON-48213" in blob      # asset tag is the point; other OCR text stays out


def test_paced_spaces_calls_to_the_free_tier_rate():
    t = [0.0]
    sleeps = []
    p = Paced(Scripted(analysis(), analysis(), analysis()), 20, clock=lambda: t[0], sleep=lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s)))
    for _ in range(3):
        p.analyze(b"x")
    assert sleeps == [3.0, 3.0]                              # 60 s / 20 calls


# ---- the gate ------------------------------------------------------------------------------------------------
def tagged(tag, conf=0.97):
    return analysis(lines=[(tag, conf)])


GOOD = [tagged("CON-48213"), tagged("CON-30571"), tagged("CON-4821O"), tagged("CON-77120"), tagged("CON-55306"), analysis()]


def test_gate_passes_on_good_reads_with_people_skipped(tmp_path):
    rep = ev.evaluate(Scripted(*GOOD), CASES, tmp_path, skip_people=True)
    assert rep.passed and rep.tag_read_rate == 1.0 and rep.wrong_tag_attached == 0
    assert "RESULT: PASS" in ev.render(rep)


def test_gate_fails_on_a_wrong_tag_attached(tmp_path):
    bad = GOOD[:]
    bad[0] = tagged("CON-48218")
    rep = ev.evaluate(Scripted(*bad), CASES, tmp_path, skip_people=True)
    assert not rep.passed and rep.wrong_tag_attached == 1 and "WRONG TAG ATTACHED" in ev.render(rep)


def test_gate_fails_when_too_few_tags_are_read(tmp_path):
    rep = ev.evaluate(Scripted(analysis(), analysis(), analysis(), analysis(), tagged("CON-55306"), analysis()), CASES, tmp_path, True)
    assert not rep.passed and rep.tag_read_rate < 0.6 and rep.wrong_tag_attached == 0


def test_gate_fails_on_a_failed_call(tmp_path):
    bad = GOOD[:]
    bad[3] = RuntimeError("boom")
    rep = ev.evaluate(Scripted(*bad), CASES, tmp_path, True)
    assert not rep.passed and rep.failed == 1


def test_missing_people_photo_fails_the_gate_unless_skipped(tmp_path):
    rep = ev.evaluate(Scripted(*GOOD), CASES, tmp_path, skip_people=False)
    assert not rep.passed and rep.people_failures == 1 and "fetch-sample" in ev.render(rep)


def test_people_case_needs_a_real_blur(tmp_path):
    (tmp_path / "learn-presentation.png").write_bytes(RAW["label-clean"])      # any image: the backend is scripted
    person = analysis(lines=[], people=[((100, 100, 300, 300), 0.9)])
    rep = ev.evaluate(Scripted(*GOOD, person), CASES, tmp_path, False)
    assert rep.passed
    none = analysis()
    rep2 = ev.evaluate(Scripted(*GOOD, none), CASES, tmp_path, False)
    assert not rep2.passed and rep2.people_failures == 1


# ---- cli -----------------------------------------------------------------------------------------------------
def test_cli_limits_and_samples(capsys, tmp_path):
    assert main(["limits"]) == 0
    out = capsys.readouterr().out
    assert "20 calls per minute" in out and "25 September 2028" in out
    assert main(["samples", "--out", str(tmp_path)]) == 0
    assert {p.name for p in tmp_path.iterdir()} >= {"label-clean.png", "label-phone-rotated.jpg", "no-tag.png"}


def test_cli_analyze_prints_decision_and_exit_code(tmp_path, capsys):
    f = tmp_path / "p.png"
    f.write_bytes(RAW["label-clean"])
    assert main(["analyze", str(f), "--out", str(tmp_path / "o")], backend=Scripted(tagged("CON-48213"))) == 0
    out = capsys.readouterr().out
    assert "attach-to-asset" in out and "the original is never written" in out
    f.write_bytes(b"junk")
    assert main(["analyze", str(f), "--out", str(tmp_path / "o")], backend=Scripted()) == 1


def test_cli_evaluate_exit_code(tmp_path):
    assert main(["evaluate", "--skip-people", "--sample-dir", str(tmp_path)], backend=Scripted(*GOOD)) == 0
    assert main(["evaluate", "--skip-people", "--sample-dir", str(tmp_path)], backend=Scripted(*([analysis()] * 6))) == 1


def test_samples_are_deterministic_and_cover_the_cases():
    assert samples.generate()["label-clean"] == samples.generate()["label-clean"]
    ids = {c["id"] for c in json.loads(CASES.read_text())["cases"]}
    assert ids - set(samples.generate()) == {"meeting-room"}


# ---- bicep ---------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("bicep"), reason="Bicep CLI not installed")
def test_bicep_keyless_free_tier_vision_resource():
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"], capture_output=True, text=True, check=True).stdout
    t = json.loads(out)
    res = list(t["resources"].values()) if isinstance(t["resources"], dict) else t["resources"]
    acct = next(r for r in res if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acct["kind"] == "ComputerVision" and acct["properties"]["disableLocalAuth"] is True
    assert acct["properties"]["customSubDomainName"]
    assert t["parameters"]["skuName"]["defaultValue"] == "F0" and t["parameters"]["location"]["defaultValue"] == "westeurope"
    role = next(r for r in res if r["type"] == "Microsoft.Authorization/roleAssignments")
    assert t["variables"]["cognitiveServicesUser"] == "a97b65f3-24c7-4388-baec-2e87135dc908" and "cognitiveServicesUser" in json.dumps(role)
