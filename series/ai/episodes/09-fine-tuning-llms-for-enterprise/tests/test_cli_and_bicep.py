import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fttriage import cli, dataset

ROOT = Path(__file__).resolve().parents[1]


def test_prepare_writes_files_and_passes_preflight(tmp_path, capsys):
    out = tmp_path / "build"
    assert cli.main(["prepare", "--out", str(out), "--price-per-million", "10", "--epochs", "3"]) == 0
    text = capsys.readouterr().out
    assert "100 train / 21 validation / 29 test + 16 golden" in text and "PREFLIGHT OK" in text
    assert "estimated training cost for 3 epochs" in text
    for name in ("training.jsonl", "validation.jsonl"):
        assert (out / name).read_bytes().startswith(b"\xef\xbb\xbf")
    assert len(dataset.read_jsonl(out / "training.jsonl")) == 100
    test = dataset.read_jsonl(out / "test.jsonl")
    assert len(test) == 45 and sum(1 for t in test if t["urgency"] is None) == 16
    train_texts = {r["messages"][1]["content"] for r in dataset.read_jsonl(out / "training.jsonl")}
    assert not train_texts & {t["text"] for t in test}


def test_prepare_fails_with_exit_1_when_a_training_example_holds_personal_data(tmp_path, capsys):
    ex = dataset.load_labelled(ROOT / "data" / "labelled.jsonl")
    victim = dataset.split(ex).train[0].id
    lines = []
    for line in (ROOT / "data" / "labelled.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d["id"] == victim:
            d["text"] = "Please send the answer to maria.santos@contoso.example"
        lines.append(json.dumps(d, ensure_ascii=False))
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert cli.main(["prepare", "--labelled", str(bad), "--out", str(tmp_path / "b")]) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out and "pii" in out and "PREFLIGHT FAILED" in out


def _cost_args(**over):
    a = {"base-prompt-tokens": 700, "tuned-prompt-tokens": 40, "completion-tokens": 20, "base-input-price": 1,
         "base-output-price": 4, "tuned-input-price": 1, "tuned-output-price": 4, "hosting-per-hour": 0.5,
         "training-cost": 12}
    a.update(over)
    return ["cost"] + [x for k, v in a.items() for x in (f"--{k}", str(v))]


def test_cost_command(capsys):
    assert cli.main(_cost_args()) == 0
    assert "break-even:" in capsys.readouterr().out
    assert cli.main(_cost_args(**{"tuned-prompt-tokens": 700, "tuned-input-price": 3})) == 0
    assert "never cheaper per call" in capsys.readouterr().out


def test_cleanup_deletes_the_deployment_then_the_uploaded_files(stub, tmp_path, monkeypatch, capsys):
    from conftest import FakeCredential
    from fttriage import deploy, jobs
    monkeypatch.setattr(deploy, "get_token", lambda c=None: "tok")
    monkeypatch.setattr(deploy, "_url", lambda s, g, a, n, m: f"{stub.url}/subscriptions/{s}/resourceGroups/{g}/providers/"
                        f"Microsoft.CognitiveServices/accounts/{a}/deployments/{n}")
    real_make_client = jobs.make_client
    monkeypatch.setattr(jobs, "make_client", lambda endpoint, credential=None: real_make_client(endpoint, FakeCredential()))
    (tmp_path / "job.json").write_text(json.dumps(jobs.asdict(jobs.JobRecord(
        "ftjob-1", "m", "Standard", "file-t", "file-v", "succeeded", "ft:m", ["file-r"]))))
    assert cli.main(["cleanup", "--subscription", "s", "--resource-group", "rg", "--account", "acc",
                     "--endpoint", stub.url, "--out", str(tmp_path)]) == 0
    deleted = [r["path"] for r in stub.requests if r["method"] == "DELETE"]
    assert deleted[0].endswith("/deployments/triage-ft")
    assert [p.rsplit("/", 1)[1] for p in deleted[1:]] == ["file-t", "file-v", "file-r"]


def test_module_entry_point_help():
    r = subprocess.run([sys.executable, "-m", "fttriage", "--help"], cwd=ROOT / "src", capture_output=True, text=True)
    assert r.returncode == 0 and all(c in r.stdout for c in ("prepare", "submit", "deploy", "evaluate", "cleanup", "cost"))


pytestmark_bicep = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True, text=True)
    t = json.loads(out.read_text())
    res = t["resources"]
    return t, list(res.values()) if isinstance(res, dict) else res


@pytestmark_bicep
def test_account_is_keyless_in_sweden_central_with_a_pinned_base_deployment(arm):
    t, res = arm
    (acc,) = [r for r in res if r["type"] == "Microsoft.CognitiveServices/accounts"]
    assert acc["properties"]["disableLocalAuth"] is True and acc["kind"] == "OpenAI"
    assert t["parameters"]["location"]["defaultValue"] == "swedencentral"
    (dep,) = [r for r in res if r["type"] == "Microsoft.CognitiveServices/accounts/deployments"]
    assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    assert dep["properties"]["model"] == {"format": "OpenAI", "name": "[parameters('baseModel')]",
                                          "version": "[parameters('baseVersion')]"}
    assert t["parameters"]["baseModel"]["defaultValue"] == "gpt-4.1-mini" and t["parameters"]["baseVersion"]["defaultValue"] == "2025-04-14"
    assert t["parameters"]["baseSku"]["defaultValue"] == "Standard"


@pytestmark_bicep
def test_developer_gets_only_the_openai_contributor_role(arm):
    t, res = arm
    ra = [r for r in res if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(ra) == 1 and ra[0]["properties"]["principalType"] == "[parameters('developerPrincipalType')]"
    assert t["variables"]["openAiContributor"] == "a001fd3d-188f-4b5d-821b-7da978bf7442"
