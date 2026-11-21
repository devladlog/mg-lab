"""The Power Platform CLI (no sign-in needed) packs the solution, and its own settings file lists what ours expects."""
import json
import shutil
import subprocess
import zipfile

from conftest import DEPLOY, RELEASE_1_0, SOLUTION, needs_pac

from almkit import load_solution, settings


def pac(*args, timeout=300):
    return subprocess.run(["pac", *args], capture_output=True, text=True, timeout=timeout)


def solution_xml(zip_path):
    return zipfile.ZipFile(zip_path).read("solution.xml").decode("utf-8-sig")


@needs_pac
def test_pack_unmanaged_and_managed(tmp_path):
    for kind, flag in (("Unmanaged", "0"), ("Managed", "1")):
        out = tmp_path / f"{kind}.zip"
        r = pac("solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION), "--packagetype", kind)
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"<Managed>{flag}</Managed>" in solution_xml(out)
        names = zipfile.ZipFile(out).namelist()
        assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 1
        assert sorted(n.split("/")[1] for n in names if n.startswith("environmentvariabledefinitions/")) == [
            "cts_EnvironmentLabel", "cts_ITRequestsList", "cts_ITSiteUrl", "cts_ServiceDeskMailbox"]


@needs_pac
def test_the_first_release_packs_too(tmp_path):
    r = pac("solution", "pack", "--zipfile", str(tmp_path / "r.zip"), "--folder", str(RELEASE_1_0), "--packagetype", "Managed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in zipfile.ZipFile(tmp_path / "r.zip").namelist()) == 2


@needs_pac
def test_managed_pack_fails_when_the_folder_was_unpacked_as_unmanaged_only(tmp_path):
    """The failure that made us write rule A02: ex-DEV folders with <Managed>0</Managed> can't be packed as managed."""
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    x = dest / "Other" / "Solution.xml"
    x.write_text(x.read_text(encoding="utf-8").replace("<Managed>2</Managed>", "<Managed>0</Managed>"), encoding="utf-8")
    r = pac("solution", "pack", "--zipfile", str(tmp_path / "m.zip"), "--folder", str(dest), "--packagetype", "Managed")
    assert r.returncode != 0
    assert "Solution package type did not match requested type" in r.stdout + r.stderr
    assert not (tmp_path / "m.zip").exists()


@needs_pac
def test_create_settings_lists_exactly_what_our_templates_contain(tmp_path):
    out = tmp_path / "s.json"
    r = pac("solution", "create-settings", "--solution-folder", str(SOLUTION), "--settings-file", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    generated = json.loads(out.read_text(encoding="utf-8"))
    ours = settings.template_for(load_solution(SOLUTION))
    assert [e["SchemaName"] for e in generated["EnvironmentVariables"]] == [e["SchemaName"] for e in ours["EnvironmentVariables"]]
    assert all(e["Value"] == "" for e in generated["EnvironmentVariables"])
    assert [(c["LogicalName"], c["ConnectorId"]) for c in generated["ConnectionReferences"]] == \
           [(c["LogicalName"], c["ConnectorId"]) for c in ours["ConnectionReferences"]]
    assert all(c["ConnectionId"] == "" for c in generated["ConnectionReferences"])
    for name in ("settings.test.json", "settings.prod.json"):
        committed = json.loads((DEPLOY / name).read_text(encoding="utf-8"))
        assert [e["SchemaName"] for e in committed["EnvironmentVariables"]] == [e["SchemaName"] for e in generated["EnvironmentVariables"]]
        assert [c["LogicalName"] for c in committed["ConnectionReferences"]] == [c["LogicalName"] for c in generated["ConnectionReferences"]]


@needs_pac
def test_create_settings_on_the_zip_equals_on_the_folder(tmp_path):
    z = tmp_path / "u.zip"
    assert pac("solution", "pack", "--zipfile", str(z), "--folder", str(SOLUTION), "--packagetype", "Unmanaged").returncode == 0
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert pac("solution", "create-settings", "--solution-zip", str(z), "--settings-file", str(a)).returncode == 0
    assert pac("solution", "create-settings", "--solution-folder", str(SOLUTION), "--settings-file", str(b)).returncode == 0
    assert json.loads(a.read_text()) == json.loads(b.read_text())


@needs_pac
def test_pac_solution_version_strategy_solution_raises_the_build_number(tmp_path):
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    r = pac("solution", "version", "--strategy", "Solution", "--solutionPath", str(dest))
    assert r.returncode == 0, r.stdout + r.stderr
    assert load_solution(dest).version_text == "1.1.1.0"  # 1.1.0.0 -> build +1
