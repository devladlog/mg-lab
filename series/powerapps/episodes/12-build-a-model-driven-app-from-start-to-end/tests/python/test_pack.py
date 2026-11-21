"""The real Power Platform CLI (pac), offline: pack, unpack, round trip. Nothing here touches a tenant."""
import zipfile
from pathlib import Path

import pytest

import build_solution
from conftest import SOLUTION, has_pac, pac

pytestmark = pytest.mark.skipif(not has_pac(), reason="pac CLI not installed")


def pack(tmp_path, folder=SOLUTION, name="ContosoInspections.zip", extra=()):
    z = tmp_path / name
    r = pac("solution", "pack", "--zipfile", z, "--folder", folder, "--packagetype", "Unmanaged", *extra)
    assert r.code == 0, r
    return z


def test_pack_writes_a_solution_zip(tmp_path):
    z = pack(tmp_path)
    names = set(zipfile.ZipFile(z).namelist())
    assert {"solution.xml", "customizations.xml", "[Content_Types].xml"} <= names
    sol = zipfile.ZipFile(z).read("solution.xml").decode("utf-8-sig")
    assert "<UniqueName>ContosoInspections</UniqueName>" in sol and "<Managed>0</Managed>" in sol


def test_pack_then_unpack_gives_back_the_same_source(tmp_path):
    z = pack(tmp_path)
    target = tmp_path / "again"
    r = pac("solution", "unpack", "--zipfile", z, "--folder", target, "--packagetype", "Unmanaged")
    assert r.code == 0, r
    mine = sorted(p.relative_to(SOLUTION).as_posix() for p in SOLUTION.rglob("*") if p.is_file())
    theirs = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    assert theirs == mine
    for rel in mine:
        assert (target / rel).read_bytes() == (SOLUTION / rel).read_bytes(), rel


def test_packed_customizations_contain_tables_roles_dashboard_app_and_field_security(tmp_path):
    z = pack(tmp_path)
    c = zipfile.ZipFile(z).read("customizations.xml").decode("utf-8-sig")
    for needle in ("<Name LocalizedName=\"Inspection\" OriginalName=\"Inspection\">cin_inspection</Name>", "<Role id=", "<Dashboard", "<AppModule>",
                   "<AppModuleSiteMap>", "<FieldSecurityProfile ", "<visualization", "<EntityRelationship Name=\"cin_site_inspection\">"):
        assert needle in c, needle


def test_a_missing_dashboard_file_still_packs_but_pac_warns_which_object_is_missing(tmp_path):
    """Gotcha: the pack exits 0. Only the log says "root components are not defined in customizations". Read it, or grep for it in a pipeline."""
    import shutil
    broken = tmp_path / "broken"
    shutil.copytree(SOLUTION, broken)
    for p in (broken / "Dashboards").glob("*.xml"):
        p.unlink()
    r = pac("solution", "pack", "--zipfile", tmp_path / "x.zip", "--folder", broken, "--packagetype", "Unmanaged")
    assert r.code == 0
    assert "root components are not defined in customizations" in r.out
    assert "5513348e-ef80-5e3b-9c80-d30848c3b4cf" in r.out


def test_a_site_map_root_component_with_a_guid_is_rejected_by_this_pac_version(tmp_path):
    """Our first attempt used id=\"{guid}\" for the app and site map roots. pac 2.16.1: 'RootComponent validation failed.'"""
    import shutil
    broken = tmp_path / "guid-roots"
    shutil.copytree(SOLUTION, broken)
    sol = broken / "Other" / "Solution.xml"
    text = sol.read_text(encoding="utf-8-sig")
    text = text.replace('<RootComponent type="80" schemaName="cin_InspectionBackOffice"', '<RootComponent type="80" id="{00000000-0000-0000-0000-000000000001}"')
    sol.write_text(text, encoding="utf-8-sig")
    r = pac("solution", "pack", "--zipfile", tmp_path / "x.zip", "--folder", broken, "--packagetype", "Unmanaged")
    assert r.code != 0 and "RootComponent validation failed" in r.out + r.err


def test_the_data_only_profile_packs_too_and_has_no_app_parts(tmp_path):
    out = tmp_path / "data"
    build_solution.main(["--profile", "data", "--out", str(out)])
    assert not (out / "AppModules").exists() and not (out / "Dashboards").exists() and not (out / "Roles").exists()
    assert len(list((out / "Entities").glob("*/Entity.xml"))) == 4
    z = pack(tmp_path, out, "data.zip")
    assert zipfile.ZipFile(z).testzip() is None


def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_solution.main(["--profile", "full", "--out", str(a)])
    build_solution.main(["--profile", "full", "--out", str(b)])
    fa = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    assert fa == sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    assert all((a / f).read_bytes() == (b / f).read_bytes() for f in fa)


def test_a_managed_zip_cannot_be_packed_from_an_unmanaged_only_source(tmp_path):
    """Why a pipeline unpacks with --packagetype Both (episode 9): our source is unmanaged only."""
    r = pac("solution", "pack", "--zipfile", tmp_path / "m.zip", "--folder", SOLUTION, "--packagetype", "Managed")
    assert r.code != 0
