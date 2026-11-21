import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import oracle
from mmticket import cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def wired(monkeypatch, client):
    monkeypatch.setattr(cli, "make_client", lambda endpoint: client)


def test_samples_command_writes_seven_pictures(tmp_path, capsys):
    assert cli.main(["samples", "--out", str(tmp_path / "i")]) == 0
    assert len(list((tmp_path / "i").glob("*.png"))) == 7 and "vpn-clean.png" in capsys.readouterr().out


def test_endpoint_is_required(monkeypatch):
    monkeypatch.delenv("MMTICKET_ENDPOINT", raising=False)
    with pytest.raises(SystemExit, match="MMTICKET_ENDPOINT"):
        cli.main(["transcribe", "x.mp3"])


def test_ticket_command_end_to_end(wired, stub, image_dir, tmp_path, capsys):
    audio = tmp_path / "n.mp3"
    audio.write_bytes(b"ID3x")
    stub.transcripts["n.mp3"] = "VPN fails with CX-4120"
    code = cli.main(["ticket", "--endpoint", "http://x", "--image", str(image_dir / "vpn-clean.png"),
                     "--audio", str(audio), "--detail", "low"])
    out = capsys.readouterr().out
    assert code == 0 and "conflict" in out and '"needs_human": true' in out and "prompt_tokens=125" in out


def test_ticket_command_reports_a_bad_image_with_exit_2(wired, tmp_path, capsys):
    bad = tmp_path / "x.png"
    bad.write_bytes(b"nope")
    assert cli.main(["ticket", "--endpoint", "http://x", "--image", str(bad)]) == 2
    assert "not a readable image" in capsys.readouterr().err


def test_voice_command_skips_cases_without_a_voice_note(wired, stub, tmp_path, capsys):
    assert cli.main(["voice", "--endpoint", "http://x", "--out", str(tmp_path)]) == 0
    assert len(stub.all("/audio/speech")) == 5 and "synthetic speech" in capsys.readouterr().out
    assert len(list(tmp_path.glob("*.mp3"))) == 5


def test_evaluate_exit_code_follows_the_gate(wired, stub, image_dir, cases, by_image, capsys):
    args = ["evaluate", "--endpoint", "http://x", "--images", str(image_dir)]
    stub.chat = oracle(by_image, cases)
    assert cli.main(args) == 0 and "RESULT: use detail=low" in capsys.readouterr().out
    stub.chat = oracle(by_image, cases, follow_injection=True)
    assert cli.main(args) == 1 and "do not ship" in capsys.readouterr().out


def test_module_entry_point_prints_help():
    r = subprocess.run([sys.executable, "-m", "mmticket", "--help"], cwd=ROOT, capture_output=True, text=True,
                       env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert r.returncode == 0 and "samples" in r.stdout and "evaluate" in r.stdout


needs_bicep = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True)
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def arm(template):
    return template["resources"]


@needs_bicep
def test_bicep_is_keyless_in_sweden_central_with_three_standard_deployments(arm):
    acct = next(r for r in arm if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acct["kind"] == "OpenAI" and acct["properties"]["disableLocalAuth"] is True
    assert acct["location"] == "[parameters('location')]"
    deps = {r["name"].split("/")[-1].strip("')]"): r for r in arm if r["type"].endswith("/deployments")}
    assert len(deps) == 3
    models = {d["properties"]["model"]["name"] for d in deps.values()}
    assert models == {"[parameters('visionModel')]", "whisper", "tts"}
    assert all(d["sku"]["name"] == "Standard" for d in deps.values())
    assert all(d["properties"]["versionUpgradeOption"] == "NoAutoUpgrade" for d in deps.values())


@needs_bicep
def test_bicep_gives_the_developer_inference_rights_only_and_creates_deployments_in_a_chain(arm, template):
    roles = [r for r in arm if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(roles) == 1
    assert "variables('openAiUser')" in json.dumps(roles[0])
    assert template["variables"]["openAiUser"] == "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"      # OpenAI User, not Contributor
    assert "a001fd3d" not in json.dumps(template)
    chained = [r for r in arm if r["type"].endswith("/deployments") and r.get("dependsOn", [])
               and any("deployments" in d for d in r["dependsOn"])]
    assert len(chained) == 2
