"""The files Visual Studio reads: .vsconfig, solution filters, .runsettings, playlists, launch profiles, snippets.
No .NET needed: these are the repository's files and tools/vs_files.py (the pipeline guard) against them."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import pytest
from conftest import APP, LEARN_IDS, SMOKE_NAMES, tool

PLAYLIST = APP / "tests" / "Contoso.Orders.Api.Tests" / "Smoke.playlist"
LAUNCH = APP / "src" / "Contoso.Orders.Api" / "Properties" / "launchSettings.json"


def learn_ids():
    return {line.strip() for line in LEARN_IDS.read_text().splitlines() if line.strip() and not line.startswith("#")}


# ---- the repository's own files -------------------------------------------------------------------------------------


def test_the_guard_passes_on_the_shipped_files():
    code, out = tool("check", ".", "--known-ids", LEARN_IDS)
    assert code == 0, out
    assert "all Visual Studio files are consistent" in out


def test_vsconfig_names_the_workload_and_the_sdk():
    data = json.loads((APP / ".vsconfig").read_text())
    assert data["version"] == "1.0"
    assert "Microsoft.VisualStudio.Workload.NetWeb" in data["components"]
    assert "Microsoft.NetCore.Component.SDK" in data["components"]
    assert len(data["components"]) == len(set(data["components"]))


def test_every_vsconfig_id_is_published_on_learn():
    ids = json.loads((APP / ".vsconfig").read_text())["components"]
    known = learn_ids()
    assert len(known) > 500, "the saved Learn list looks empty"
    assert [i for i in ids if i not in known] == []


def test_vsconfig_sits_next_to_the_solution():
    assert (APP / ".vsconfig").is_file() and (APP / "OrdersApp.slnx").is_file()


def test_solution_filters_name_projects_of_the_solution():
    solution = (APP / "OrdersApp.slnx").read_text()
    listed = set(re.findall(r'<Project Path="([^"]+)"', solution))
    for name, expected in (("OrdersApp.Api.slnf", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj"),
                           ("OrdersApp.Tests.slnf", "tests/Contoso.Orders.Api.Tests/Contoso.Orders.Api.Tests.csproj")):
        data = json.loads((APP / name).read_text())["solution"]
        assert data["path"] == "OrdersApp.slnx"
        assert [p.replace("\\", "/") for p in data["projects"]] == [expected]
        assert expected in listed
    assert "\\" in (APP / "OrdersApp.Api.slnf").read_text(), "Visual Studio writes the project paths with backslashes"


def test_the_props_file_points_every_runner_at_the_runsettings():
    props = (APP / "Directory.Build.props").read_text()
    assert "<RunSettingsFilePath>$(MSBuildThisFileDirectory).runsettings</RunSettingsFilePath>" in props
    assert (APP / ".runsettings").is_file()


def test_runsettings_values():
    run = ET.parse(APP / ".runsettings").getroot().find("RunConfiguration")
    assert run.findtext("MaxCpuCount") == "1"
    assert run.findtext("TestSessionTimeout") == "300000"
    assert run.findtext("TreatNoTestsAsError") == "true"
    assert run.find("EnvironmentVariables").findtext("CONTOSO_REGION") == "lab-west"


def test_the_playlist_selects_the_smoke_trait_that_the_tests_carry():
    traits = [(p.get("Value")) for p in ET.parse(PLAYLIST).getroot().iter("Property") if p.get("Name") == "Trait"]
    assert traits == ["Category [Smoke]"]
    sources = "".join(p.read_text() for p in (APP / "tests").rglob("*.cs"))
    assert sources.count('Trait("Category", "Smoke")') == SMOKE_NAMES


def test_launch_profiles_have_distinct_ports_and_the_hot_reload_switch():
    profiles = json.loads(LAUNCH.read_text())["profiles"]
    urls = [p["applicationUrl"] for p in profiles.values()]
    assert len(urls) == len(set(urls)) == 3
    assert profiles["Orders API (20 orders, OpenAPI)"]["hotReloadEnabled"] is True
    assert profiles["Orders API (no Hot Reload)"]["hotReloadEnabled"] is False
    assert profiles["Orders API (20 orders, OpenAPI)"]["environmentVariables"]["Orders__SeedCount"] == "20"


def test_the_second_snippet_is_a_surround_with_and_the_first_an_expansion():
    kinds = {}
    for path in (APP / "snippets").glob("*.snippet"):
        ns = {"s": "http://schemas.microsoft.com/VisualStudio/2005/CodeSnippet"}
        root = ET.parse(path).getroot()
        kinds[root.findtext(".//s:Shortcut", namespaces=ns)] = root.findtext(".//s:SnippetType", namespaces=ns)
    assert kinds == {"ordtest": "Expansion", "ordscope": "SurroundsWith"}


# ---- the guard catches what it says it catches ----------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    """A tiny repository with one of each file, all valid."""
    (tmp_path / "A.slnx").write_text('<Solution><Project Path="src/A/A.csproj" /></Solution>')
    (tmp_path / "src" / "A").mkdir(parents=True)
    (tmp_path / "src" / "A" / "A.csproj").write_text("<Project />")
    (tmp_path / "A.slnf").write_text(json.dumps({"solution": {"path": "A.slnx", "projects": ["src\\A\\A.csproj"]}}))
    (tmp_path / ".vsconfig").write_text(json.dumps({"version": "1.0", "components": ["X.One", "X.Two"]}))
    (tmp_path / "t.runsettings").write_text("<RunSettings><RunConfiguration><MaxCpuCount>1</MaxCpuCount></RunConfiguration></RunSettings>")
    (tmp_path / "ids.txt").write_text("# comment\nX.One\nX.Two\n")
    return tmp_path


def problems(repo, *extra):
    code, out = tool("check", repo, "--known-ids", repo / "ids.txt", *extra)
    return code, out


def test_guard_accepts_the_valid_tiny_repository(repo):
    assert problems(repo)[0] == 0


def test_guard_flags_the_misspelled_max_cpu_count(repo):
    (repo / "t.runsettings").write_text("<RunSettings><RunConfiguration><MaxCPUCount>0</MaxCPUCount></RunConfiguration></RunSettings>")
    code, out = problems(repo)
    assert code == 1 and "MaxCPUCount is ignored" in out


def test_guard_flags_a_zero_timeout_and_a_wrong_root(repo):
    (repo / "t.runsettings").write_text("<RunSettings><RunConfiguration><TestSessionTimeout>0</TestSessionTimeout></RunConfiguration></RunSettings>")
    assert "must be greater than 0" in problems(repo)[1]
    (repo / "t.runsettings").write_text("<Settings />")
    assert "root element must be RunSettings" in problems(repo)[1]


def test_guard_flags_an_unknown_and_a_duplicated_component(repo):
    (repo / ".vsconfig").write_text(json.dumps({"version": "1.0", "components": ["X.One", "X.One", "Y.Nope"]}))
    out = problems(repo)[1]
    assert "X.One is listed more than once" in out and "Y.Nope is not a workload or component ID" in out


def test_guard_flags_a_vsconfig_away_from_the_solution(repo):
    (repo / "sub").mkdir()
    (repo / "sub" / ".vsconfig").write_text(json.dumps({"version": "1.0", "components": ["X.One"]}))
    assert "next to the solution" in problems(repo)[1]


def test_guard_flags_a_filter_with_a_project_that_is_not_in_the_solution(repo):
    (repo / "A.slnf").write_text(json.dumps({"solution": {"path": "A.slnx", "projects": ["src\\B\\B.csproj"]}}))
    code, out = problems(repo)
    assert code == 1 and "is not a project of A.slnx" in out


def test_guard_flags_a_filter_without_its_solution_and_an_empty_filter(repo):
    (repo / "A.slnf").write_text(json.dumps({"solution": {"path": "Gone.slnx", "projects": ["x"]}}))
    assert "does not exist" in problems(repo)[1]
    (repo / "A.slnf").write_text(json.dumps({"solution": {"path": "A.slnx", "projects": []}}))
    assert "would load and build nothing" in problems(repo)[1]


def test_guard_flags_two_launch_profiles_on_one_port(repo):
    folder = repo / "src" / "A" / "Properties"
    folder.mkdir()
    (folder / "launchSettings.json").write_text(json.dumps({"profiles": {
        "one": {"commandName": "Project", "applicationUrl": "http://localhost:5000"},
        "two": {"commandName": "Project", "applicationUrl": "http://localhost:5000"}}}))
    assert "both use http://localhost:5000" in problems(repo)[1]


SNIPPET = """<CodeSnippets xmlns="http://schemas.microsoft.com/VisualStudio/2005/CodeSnippet"><CodeSnippet Format="1.0.0">
<Header><Title>t</Title><Shortcut>{shortcut}</Shortcut></Header><Snippet>
<Declarations>{literals}</Declarations><Code Language="CSharp"><![CDATA[{code}]]></Code></Snippet></CodeSnippet></CodeSnippets>"""
LITERAL = "<Literal><ID>{id}</ID><Default>{default}</Default></Literal>"


def write_snippet(repo, name="a.snippet", shortcut="a", literals=("x",), code="$x$", defaults=True):
    lits = "".join(LITERAL.format(id=i, default="d") if defaults else f"<Literal><ID>{i}</ID></Literal>" for i in literals)
    (repo / name).write_text(SNIPPET.format(shortcut=shortcut, literals=lits, code=code))


def test_guard_flags_an_undeclared_and_an_unused_placeholder(repo):
    write_snippet(repo, literals=("x", "unused"), code="$x$ $missing$")
    out = problems(repo)[1]
    assert "$missing$ is used in the code but not declared" in out and "literal unused is declared but never used" in out


def test_guard_flags_selected_twice_a_missing_default_and_a_reserved_id(repo):
    write_snippet(repo, code="$selected$ and $selected$ $x$")
    assert "$selected$ appears more than once" in problems(repo)[1]
    write_snippet(repo, defaults=False)
    assert "needs exactly one Default" in problems(repo)[1]
    write_snippet(repo, literals=("x", "end"), code="$x$ $end$")
    assert "end is reserved" in problems(repo)[1]


def test_guard_flags_a_shortcut_used_twice(repo):
    write_snippet(repo, "a.snippet", "dup")
    write_snippet(repo, "b.snippet", "dup")
    assert "shortcut 'dup' is also used by a.snippet" in problems(repo)[1]


def test_guard_flags_a_snippet_that_is_not_xml(repo):
    (repo / "bad.snippet").write_text("<CodeSnippets>")
    assert "not well-formed XML" in problems(repo)[1]


# ---- the snippet expander follows the documented rules --------------------------------------------------------------


def test_expand_uses_defaults_and_empties_the_end_marker():
    code, out = tool("expand", APP / "snippets" / "ordtest.snippet")
    assert code == 0
    assert "public async Task Orders_list_answers_200()" in out
    assert 'GetAsync("/orders")' in out and "HttpStatusCode.OK" in out and "$" not in out


def test_expand_takes_replacements_for_literals():
    code, out = tool("expand", APP / "snippets" / "ordtest.snippet", "--set", "path=/orders/99999", "--set", "status=NotFound")
    assert code == 0 and 'GetAsync("/orders/99999")' in out and "HttpStatusCode.NotFound" in out


def test_expand_puts_the_selection_where_selected_is():
    code, out = tool("expand", APP / "snippets" / "ordscope.snippet", "--selected", "DoWork();", "--set", "step=import")
    assert code == 0
    assert 'BeginScope("import")' in out and "DoWork();" in out
    assert out.index("DoWork();") > out.index("{")


def test_expand_honors_a_custom_delimiter(tmp_path):
    path = tmp_path / "d.snippet"
    path.write_text('<CodeSnippets xmlns="http://schemas.microsoft.com/VisualStudio/2005/CodeSnippet"><CodeSnippet><Header><Title>t</Title></Header>'
                    '<Snippet><Declarations><Literal><ID>n</ID><Default>5</Default></Literal></Declarations>'
                    '<Code Language="CSharp" Delimiter="@"><![CDATA[var cost = $5 + @n@;]]></Code></Snippet></CodeSnippet></CodeSnippets>')
    code, out = tool("expand", path)
    assert code == 0 and "var cost = $5 + 5;" in out
