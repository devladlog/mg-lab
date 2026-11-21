"""Update or Upgrade: what a new release removes decides it."""
import shutil

from conftest import RELEASE_1_0, SOLUTION, codes

from almkit import checks, diff, load_solution


def test_release_1_1_removes_a_flow_and_a_variable_so_it_needs_an_upgrade():
    plan = diff.plan(load_solution(RELEASE_1_0), load_solution(SOLUTION))
    assert plan.flows_removed == ["Weekly stale summary"]
    assert plan.env_removed == ["cts_StaleDays"]
    assert plan.flows_added == [] and plan.flows_changed == [] and plan.refs_removed == []
    assert plan.needs_upgrade and not plan.needs_new_settings
    assert "UPGRADE" in "\n".join(plan.lines())


def test_going_the_other_way_adds_things_so_an_update_is_enough_but_settings_need_a_new_entry():
    plan = diff.plan(load_solution(SOLUTION), load_solution(RELEASE_1_0))
    assert plan.flows_added == ["Weekly stale summary"] and plan.env_added == ["cts_StaleDays"]
    assert not plan.needs_upgrade and plan.needs_new_settings


def test_same_folder_is_no_change():
    plan = diff.plan(load_solution(SOLUTION), load_solution(SOLUTION))
    assert not plan.needs_upgrade and plan.flows_changed == []


def test_a_changed_flow_is_reported(tmp_path):
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    p = next((dest / "Workflows").glob("*.json"))
    p.write_text(p.read_text(encoding="utf-8").replace("received", "got"), encoding="utf-8")
    plan = diff.plan(load_solution(SOLUTION), load_solution(dest))
    assert plan.flows_changed == ["Acknowledge IT request"]


def test_a_changed_default_is_reported(tmp_path):
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    x = dest / "environmentvariabledefinitions" / "cts_EnvironmentLabel" / "environmentvariabledefinition.xml"
    x.write_text(x.read_text().replace("<defaultvalue>DEV</defaultvalue>", "<defaultvalue>LAB</defaultvalue>"))
    assert diff.plan(load_solution(SOLUTION), load_solution(dest)).env_default_changed == ["cts_EnvironmentLabel"]


def test_version_must_go_up():
    old, new = load_solution(RELEASE_1_0), load_solution(SOLUTION)
    assert checks.check_version_bump(old, new) == []
    f = checks.check_version_bump(new, new)
    assert codes(f) == ["V02"] and "not higher" in f[0].message
    assert codes(checks.check_version_bump(new, old)) == ["V02"]


def test_version_compares_numbers_not_text(tmp_path):
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    x = dest / "Other" / "Solution.xml"
    x.write_text(x.read_text(encoding="utf-8").replace("<Version>1.1.0.0", "<Version>1.10.0.0"), encoding="utf-8")
    assert checks.check_version_bump(load_solution(SOLUTION), load_solution(dest)) == []  # 1.10 > 1.1, "1.10" < "1.2" as text


def test_another_solution_is_not_a_new_version(tmp_path):
    dest = tmp_path / "s"
    shutil.copytree(SOLUTION, dest)
    x = dest / "Other" / "Solution.xml"
    x.write_text(x.read_text(encoding="utf-8").replace("<UniqueName>ITRequestNotices", "<UniqueName>Other"), encoding="utf-8")
    assert codes(checks.check_version_bump(load_solution(RELEASE_1_0), load_solution(dest))) == ["V01"]
