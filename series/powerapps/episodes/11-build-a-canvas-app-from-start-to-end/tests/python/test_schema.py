"""The shared ContosoInspections schema (src/schema) is the one source for the provisioning script, the test harness and the
model-driven and agent specials. These checks keep it reusable: consistent prefix, no dangling references, fictional data only."""
import json
import re

from conftest import EPISODE, SRC

ROLE_DEPTHS = {"Basic", "Local", "Deep", "Global"}
ROLE_VERBS = {"Create", "Read", "Write", "Delete", "Append", "AppendTo", "Assign", "Share"}


def tables(schema):
    return {t["schemaName"]: t for t in schema["tables"]}


def test_publisher_and_solution_follow_the_series_contract(schema):
    s = schema["solution"]
    assert s["uniqueName"] == "ContosoInspections"
    assert s["publisher"]["prefix"] == "cin"
    assert s["publisher"]["uniqueName"] == "contosolab"
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", s["version"])
    # Learn: the option value prefix is a number from 10000 to 99999.
    assert 10000 <= s["publisher"]["optionValuePrefix"] <= 99999


def test_there_are_four_tables_and_every_name_has_the_publisher_prefix(schema):
    names = list(tables(schema))
    assert names == ["cin_Site", "cin_Inspector", "cin_Inspection", "cin_Finding"]
    for t in schema["tables"]:
        assert t["schemaName"].startswith("cin_")
        assert t["primaryName"]["schemaName"].startswith("cin_")
        assert t["ownership"] in {"UserOwned", "OrganizationOwned"}
        for c in t["columns"]:
            assert c["schemaName"].startswith("cin_"), c["schemaName"]


def test_names_are_unique_per_table_and_display_names_do_not_collide_with_system_columns(schema):
    for t in schema["tables"]:
        cols = [t["primaryName"]["schemaName"]] + [c["schemaName"] for c in t["columns"]]
        assert len(cols) == len({c.lower() for c in cols})
        shown = [t["primaryName"]["displayName"]] + [c["displayName"] for c in t["columns"]]
        assert len(shown) == len(set(shown)), t["schemaName"]
        # A custom column called "Status" would sit next to the system Status (statecode) in Power Fx; keep it distinct.
        assert "Status" not in shown, t["schemaName"]


def test_column_types_are_ones_the_provisioner_and_the_harness_know(schema):
    known = {"string", "memo", "date", "boolean", "choice", "image"}
    for t in schema["tables"]:
        for c in t["columns"]:
            assert c["type"] in known, c["schemaName"]
            if c["type"] in {"string", "memo"}:
                assert c["maxLength"] > 0
            if c["type"] == "choice":
                assert len(c["options"]) == len(set(c["options"])) >= 2
            if c["type"] == "boolean":
                assert {"trueLabel", "falseLabel", "default"} <= set(c)
            if c["type"] == "image":
                assert c["maxSizeKB"] > 0


def test_relationships_point_at_real_tables_and_the_finding_belongs_to_its_inspection(schema):
    t = tables(schema)
    seen = set()
    for r in schema["relationships"]:
        assert r["referenced"] in t and r["referencing"] in t
        assert r["schemaName"] not in seen
        seen.add(r["schemaName"])
        assert r["lookup"]["schemaName"].startswith("cin_")
        assert r["cascade"] in {"Parental", "Referential"}
    parental = [r for r in schema["relationships"] if r["cascade"] == "Parental"]
    assert [(r["referenced"], r["referencing"]) for r in parental] == [("cin_Inspection", "cin_Finding")]


def test_user_owned_tables_are_the_ones_the_role_scopes_to_own_records(schema):
    owned = {t["schemaName"].lower() for t in schema["tables"] if t["ownership"] == "UserOwned"}
    role = {p["table"]: p for p in schema["securityRole"]["privileges"]}
    for name in owned:
        for verb in ("Create", "Read", "Write", "Append", "AppendTo"):
            assert role[name][verb] == "Basic", (name, verb)
    # Organization-owned tables can only be Global or none: Basic isn't meaningful there.
    for name in ("cin_site", "cin_inspector"):
        assert role[name]["Read"] == "Global"


def test_role_privileges_use_known_verbs_and_depths_and_name_their_schema(schema):
    for p in schema["securityRole"]["privileges"]:
        assert p["schemaName"]
        for k, v in p.items():
            if k in {"table", "schemaName", "why"}:
                continue
            assert k in ROLE_VERBS, k
            assert v in ROLE_DEPTHS, (p["table"], k, v)


def test_the_role_can_read_what_an_offline_capable_app_needs(schema):
    # Learn (set up mobile offline for canvas apps): the role also needs read on the app and the offline system tables.
    tables_read = {p["table"] for p in schema["securityRole"]["privileges"] if "Read" in p}
    assert {"canvasapp", "mobileofflineprofile", "syncerror"} <= tables_read | {t.replace("_", "") for t in tables_read}


def test_sample_data_is_fictional_and_covers_the_demo(schema):
    d = schema["sampleData"]
    assert [i["name"] for i in d["inspectors"]] == ["Alex Demo", "Sam Demo"]
    for i in d["inspectors"]:
        assert i["defaultEmail"].endswith("@contoso.com")
    risks = next(c for c in tables(schema)["cin_Site"]["columns"] if c["schemaName"] == "cin_RiskRating")["options"]
    assert all(s["risk"] in risks for s in d["sites"])
    assert len({s["code"] for s in d["sites"]}) == len(d["sites"])


def test_no_real_tenant_names_or_non_zero_guids_anywhere_in_the_episode_source():
    guid = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    bad = []
    for path in (EPISODE).rglob("*"):
        if not path.is_file() or any(p in path.parts for p in ("bin", "obj", "node_modules", ".pytest_cache", "__pycache__")):
            continue
        if path.suffix not in {".md", ".yaml", ".yml", ".json", ".xml", ".ps1", ".cs", ".py", ".csproj"} or path.name == "pa.schema.yaml":
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if path.name == "test_schema.py":
            continue
        if re.search(r"devlad" + r"log\.onmicrosoft|\.crm\d*\.dynamics\.com/(?!api)|sharepoint\.com", text, re.I) and "contoso" not in text:
            bad.append(f"{path.name}: tenant-looking url")
        for m in guid.findall(text):
            # "Zero GUIDs": 00000000-0000-0000-0000-00000000000N (a counter in the last group) is fine, anything else is not.
            if not m.startswith("00000000-0000-0000-0000-"):
                bad.append(f"{path.relative_to(EPISODE)}: {m}")
    assert not bad, bad


def test_the_schema_is_valid_json_with_a_stable_shape():
    raw = (SRC / "schema" / "contosoinspections.schema.json").read_text(encoding="utf-8")
    assert json.loads(raw)
    assert raw.endswith("\n")
