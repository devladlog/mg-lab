"""The real Power Platform CLI (pac), offline: pack, unpack, version, settings. Nothing here touches a tenant."""
import json
import re
import shutil
import zipfile
from pathlib import Path

from conftest import SOLUTION, pac, pwsh


def read_solution_xml(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return z.read("solution.xml").decode("utf-8-sig")


def pack(source, out):
    r = pwsh("Invoke-SolutionPack.ps1", "-SourcePath", source, "-OutputDirectory", out)
    assert r.code == 0, r
    unmanaged, managed = [Path(x) for x in r.out.strip().splitlines()[-2:]]
    return unmanaged, managed


def test_pack_writes_an_unmanaged_and_a_managed_zip_named_after_the_version(tmp_path):
    unmanaged, managed = pack(SOLUTION, tmp_path / "out")
    assert unmanaged.name == "EquipmentDesk_1_0_0_0.zip"
    assert managed.name == "EquipmentDesk_1_0_0_0_managed.zip"
    assert "<Managed>0</Managed>" in read_solution_xml(unmanaged)
    assert "<Managed>1</Managed>" in read_solution_xml(managed)


def test_both_zips_contain_the_environment_variable_definition(tmp_path):
    for z in pack(SOLUTION, tmp_path / "out"):
        names = zipfile.ZipFile(z).namelist()
        assert "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml" in names
        assert {"solution.xml", "customizations.xml", "[Content_Types].xml"} <= set(names)


def test_pack_then_unpack_as_both_gives_back_the_same_source(tmp_path):
    unmanaged, _ = pack(SOLUTION, tmp_path / "out")
    target = tmp_path / "unpacked"
    r = pac("solution", "unpack", "--zipfile", unmanaged, "--folder", target, "--packagetype", "Both")
    assert r.code == 0, r
    mine = sorted(p.relative_to(SOLUTION).as_posix() for p in SOLUTION.rglob("*") if p.is_file())
    theirs = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    assert theirs == mine
    for rel in mine:
        assert (target / rel).read_bytes() == (SOLUTION / rel).read_bytes(), rel


def test_a_source_unpacked_as_unmanaged_cannot_be_packed_as_managed(tmp_path):
    """Why the export pipeline exports twice and unpacks as Both (Learn: SolutionPackager, /PackageType:Both)."""
    unmanaged, _ = pack(SOLUTION, tmp_path / "out")
    only_unmanaged = tmp_path / "unmanaged-only"
    r = pac("solution", "unpack", "--zipfile", unmanaged, "--folder", only_unmanaged, "--packagetype", "Unmanaged")
    assert r.code == 0, r
    assert "<Managed>0</Managed>" in (only_unmanaged / "Other/Solution.xml").read_text(encoding="utf-8-sig")
    r = pac("solution", "pack", "--zipfile", tmp_path / "x.zip", "--folder", only_unmanaged, "--packagetype", "Managed")
    assert r.code != 0
    assert "did not match requested type" in r.out


def test_unpack_leaves_files_of_removed_components_behind(tmp_path):
    unmanaged, _ = pack(SOLUTION, tmp_path / "out")
    target = tmp_path / "source"
    stale = target / "environmentvariabledefinitions/contoso_Removed/environmentvariabledefinition.xml"
    stale.parent.mkdir(parents=True)
    stale.write_text("<environmentvariabledefinition schemaname='contoso_Removed' />")
    r = pac("solution", "unpack", "--zipfile", unmanaged, "--folder", target, "--packagetype", "Both")
    assert r.code == 0, r
    assert "Not deleting files" in r.out
    assert stale.exists()


def test_sync_removes_what_the_new_unpack_no_longer_has_and_lints_the_result(tmp_path, source_copy):
    unmanaged, _ = pack(SOLUTION, tmp_path / "out")
    fresh = tmp_path / "fresh"
    assert pac("solution", "unpack", "--zipfile", unmanaged, "--folder", fresh, "--packagetype", "Both").code == 0
    stale = source_copy / "environmentvariabledefinitions/contoso_Removed/environmentvariabledefinition.xml"
    stale.parent.mkdir(parents=True)
    stale.write_text("<environmentvariabledefinition schemaname='contoso_Removed' />")
    r = pwsh("Sync-SolutionSource.ps1", "-UnpackedPath", fresh, "-SourcePath", source_copy)
    assert r.code == 0, r
    assert "removed  environmentvariabledefinitions/contoso_Removed/environmentvariabledefinition.xml" in r.out
    assert not stale.exists()
    assert "passed all checks" in r.out


def test_sync_refuses_a_folder_that_is_not_an_unpacked_solution(tmp_path, source_copy):
    empty = tmp_path / "empty"
    empty.mkdir()
    before = sorted(p.name for p in source_copy.rglob("*"))
    r = pwsh("Sync-SolutionSource.ps1", "-UnpackedPath", empty, "-SourcePath", source_copy)
    assert r.code != 0
    assert "nothing was changed" in r.out
    assert sorted(p.name for p in source_copy.rglob("*")) == before


def test_sync_reports_added_and_changed_files(tmp_path, source_copy):
    fresh = tmp_path / "fresh"
    shutil.copytree(SOLUTION, fresh)
    extra = fresh / "environmentvariabledefinitions/contoso_Extra"
    extra.mkdir()
    shutil.copy(SOLUTION / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml", extra)
    text = (extra / "environmentvariabledefinition.xml").read_text().replace("contoso_ReminderDomain", "contoso_Extra")
    (extra / "environmentvariabledefinition.xml").write_text(text)
    p = fresh / "Other/Solution.xml"
    p.write_text(p.read_text(encoding="utf-8-sig").replace("<Version>1.0.0.0</Version>", "<Version>1.1.0.0</Version>"), encoding="utf-8-sig")
    r = pwsh("Sync-SolutionSource.ps1", "-UnpackedPath", fresh, "-SourcePath", source_copy)
    assert "added    environmentvariabledefinitions/contoso_Extra/environmentvariabledefinition.xml" in r.out, r
    assert "changed  Other/Solution.xml" in r.out, r


def test_set_solution_version_stamps_build_and_revision(source_copy):
    r = pwsh("Set-SolutionVersion.ps1", "-Path", source_copy, "-BuildVersion", 20261121, "-RevisionVersion", 3)
    assert r.code == 0, r
    assert r.out.strip().splitlines()[-1] == "1.0.20261121.3"
    assert "<Version>1.0.20261121.3</Version>" in (source_copy / "Other/Solution.xml").read_text(encoding="utf-8-sig")


def test_a_stamped_source_packs_to_zips_that_carry_the_new_version(tmp_path, source_copy):
    assert pwsh("Set-SolutionVersion.ps1", "-Path", source_copy, "-BuildVersion", 20261121, "-RevisionVersion", 3).code == 0
    unmanaged, managed = pack(source_copy, tmp_path / "out")
    assert managed.name == "EquipmentDesk_1_0_20261121_3_managed.zip"
    assert "<Version>1.0.20261121.3</Version>" in read_solution_xml(managed)


def test_pac_takes_the_build_and_the_revision_in_separate_calls_only(source_copy):
    """Observed with pac 2.16.1: both in one call is rejected, which is why Set-SolutionVersion calls it twice."""
    r = pac("solution", "version", "--buildversion", 5, "--revisionversion", 6, "--solutionPath", source_copy)
    assert r.code != 0
    assert "Must provide either --buildversion or --revisionversion" in r.out


def test_set_solution_version_rejects_a_folder_without_solution_xml(tmp_path):
    r = pwsh("Set-SolutionVersion.ps1", "-Path", tmp_path, "-BuildVersion", 1, "-RevisionVersion", 1)
    assert r.code != 0 and "No Other/Solution.xml" in r.out


def test_pac_finds_the_environment_variable_and_both_connection_references(tmp_path):
    _, managed = pack(SOLUTION, tmp_path / "out")
    out = tmp_path / "pac-settings.json"
    r = pac("solution", "create-settings", "--solution-zip", managed, "--settings-file", out)
    assert r.code == 0, r
    data = json.loads(out.read_text())
    assert [e["SchemaName"] for e in data["EnvironmentVariables"]] == ["contoso_ReminderDomain"]
    assert data["EnvironmentVariables"][0]["DefaultValue"] == "contoso.com"
    assert sorted(c["LogicalName"] for c in data["ConnectionReferences"]) == ["contoso_EquipmentDeskDataverse", "contoso_EquipmentDeskOutlook"]
    assert all(c["ConnectionId"] == "" for c in data["ConnectionReferences"])


def test_get_package_finds_the_one_managed_zip_and_sets_the_pipeline_variable(tmp_path):
    (tmp_path / "EquipmentDesk_1_0_1_2.zip").write_text("x")
    (tmp_path / "EquipmentDesk_1_0_1_2_managed.zip").write_text("x")
    r = pwsh("Get-Package.ps1", "-Directory", tmp_path, "-SetVariable", "managedZip")
    assert r.code == 0, r
    lines = r.out.strip().splitlines()
    assert lines[0] == f"##vso[task.setvariable variable=managedZip]{tmp_path}/EquipmentDesk_1_0_1_2_managed.zip"
    assert lines[1] == f"{tmp_path}/EquipmentDesk_1_0_1_2_managed.zip"


def test_get_package_refuses_zero_or_several_managed_zips(tmp_path):
    r = pwsh("Get-Package.ps1", "-Directory", tmp_path)
    assert r.code != 0 and "found 0" in r.out
    (tmp_path / "A_managed.zip").write_text("x")
    (tmp_path / "B_managed.zip").write_text("x")
    r = pwsh("Get-Package.ps1", "-Directory", tmp_path)
    assert r.code != 0 and "found 2" in r.out
