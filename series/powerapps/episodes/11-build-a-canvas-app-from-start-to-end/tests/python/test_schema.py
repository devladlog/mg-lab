"""The ContosoInspections schema in src/schema is an exact copy of episode 12's (the canonical file): one Dataverse solution, two apps.
These checks keep the copy honest and keep it usable by the canvas app: consistent prefix, no dangling references, display names that
stay unique in Power Fx, and fictional sample data only."""
import json
import re

from conftest import CANONICAL_SCHEMA_PATH, EPISODE, SCHEMA_PATH, SEED_PATH, SRC

ROLE_DEPTHS = {"Basic", "Local", "Deep", "Global"}
ROLE_VERBS = {"Create", "Read", "Write", "Delete", "Append", "AppendTo", "Assign", "Share"}
KNOWN_TYPES = {"string", "email", "phone", "memo", "date", "bool", "whole", "choice", "lookup", "image"}


def tables(schema):
    return {t["logicalName"]: t for t in schema["tables"]}


def test_the_schema_is_a_byte_for_byte_copy_of_episode_12s():
    assert CANONICAL_SCHEMA_PATH.exists(), CANONICAL_SCHEMA_PATH
    assert SCHEMA_PATH.read_bytes() == CANONICAL_SCHEMA_PATH.read_bytes(), (
        "src/schema/contosoinspections.schema.json differs from episode 12's. Episode 12 owns the schema: copy its file over this one "
        "(cp), then update the canvas app, the provisioner and the tests that depend on the change.")


def test_publisher_and_solution_follow_the_series_contract(schema):
    assert schema["solution"]["uniqueName"] == "ContosoInspections"
    assert schema["publisher"]["prefix"] == "cin"
    assert schema["publisher"]["uniqueName"] == "contosolab"
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", schema["version"])
    # Learn: the option value prefix is a number from 10000 to 99999.
    assert 10000 <= schema["publisher"]["optionValuePrefix"] <= 99999


def test_there_are_four_tables_and_every_name_has_the_publisher_prefix(schema):
    assert list(tables(schema)) == ["cin_inspector", "cin_site", "cin_inspection", "cin_inspectionitem"]
    for t in schema["tables"]:
        assert t["primaryName"]["logicalName"].startswith("cin_")
        assert t["ownership"] in {"UserOwned", "OrganizationOwned"}
        for c in t["columns"]:
            assert c["logicalName"].startswith("cin_"), c["logicalName"]


def test_names_are_unique_per_table_so_the_app_can_use_display_names(schema):
    for t in schema["tables"]:
        cols = [t["primaryName"]["logicalName"]] + [c["logicalName"] for c in t["columns"]]
        assert len(cols) == len(set(cols)), t["logicalName"]
        # In a canvas app columns are addressed by display name, and the primary key is displayed with the table's name.
        shown = [t["displayName"], t["primaryName"]["displayName"]] + [c["displayName"] for c in t["columns"]]
        assert len(shown) == len(set(shown)), (t["logicalName"], shown)


def test_the_two_columns_called_status_are_known_and_the_app_uses_the_logical_name():
    # The custom Status (cin_status) shares its display name with the system Status (statecode). The README gotcha explains why the
    # app writes cin_status; this guards that nobody "tidies" it back to a display name without checking in Studio.
    app = (SRC / "app" / "Src" / "App.pa.yaml").read_text(encoding="utf-8")
    assert "cin_status" in app
    for screen in (SRC / "app" / "Src").glob("*.pa.yaml"):
        assert not re.search(r"\.'?Status'?(?![\w( ])", screen.read_text(encoding="utf-8").replace("'Status (Inspections)'", "")), screen.name


def test_column_types_are_ones_the_provisioner_and_the_harness_know(schema):
    for t in schema["tables"]:
        for c in t["columns"]:
            assert c["type"] in KNOWN_TYPES, c["logicalName"]
            if c["type"] in {"string", "email", "phone", "memo"}:
                assert c["maxLength"] > 0
            if c["type"] == "choice":
                labels = [o[0] for o in c["options"]]
                values = [o[1] for o in c["options"]]
                assert len(labels) == len(set(labels)) >= 2 and len(values) == len(set(values))
                assert c.get("default", 0) in values
            if c["type"] == "image":
                assert c["maxSizeKB"] > 0
            if c["type"] == "lookup":
                assert c["target"] in tables(schema)


def test_relationships_point_at_real_tables_and_lookups_and_the_item_belongs_to_its_inspection(schema):
    t = tables(schema)
    names = set()
    for r in schema["relationships"]:
        assert r["referenced"] in t and r["referencing"] in t
        assert r["name"] not in names
        names.add(r["name"])
        lookup = next(c for c in t[r["referencing"]]["columns"] if c["logicalName"] == r["lookup"])
        assert lookup["type"] == "lookup" and lookup["target"] == r["referenced"]
        assert r["delete"] in {"Restrict", "RemoveLink", "Cascade"}
    # Every lookup column has exactly one relationship: the provisioner creates the lookup with it.
    lookups = {(tn, c["logicalName"]) for tn, tab in t.items() for c in tab["columns"] if c["type"] == "lookup"}
    assert lookups == {(r["referencing"], r["lookup"]) for r in schema["relationships"]}
    parental = [r for r in schema["relationships"] if r.get("parental")]
    assert [(r["referenced"], r["referencing"]) for r in parental] == [("cin_inspection", "cin_inspectionitem")]


def test_the_status_choice_is_the_shared_flow(schema):
    status = next(c for c in tables(schema)["cin_inspection"]["columns"] if c["logicalName"] == "cin_status")
    assert [o[0] for o in status["options"]] == ["Draft", "In progress", "Submitted", "Approved", "Rejected"]
    assert [o[1] for o in status["options"]] == [0, 1, 2, 3, 4]


def test_the_canvas_app_has_the_columns_it_needs(schema):
    t = tables(schema)
    inspection = {c["logicalName"] for c in t["cin_inspection"]["columns"]}
    item = {c["logicalName"]: c for c in t["cin_inspectionitem"]["columns"]}
    assert {"cin_siteid", "cin_inspectorid", "cin_inspectiondate", "cin_status", "cin_score", "cin_summary",
            "cin_requiresfollowup", "cin_followupdate"} <= inspection
    assert {"cin_inspectionid", "cin_category", "cin_severity", "cin_passed", "cin_notes", "cin_resolvedon", "cin_photo"} <= set(item)
    assert item["cin_photo"]["type"] == "image"   # the one column episode 11 asked episode 12 to add
    assert {c["logicalName"] for c in t["cin_inspector"]["columns"]} >= {"cin_email"}   # how the app recognises the signed-in user
    assert t["cin_inspection"]["primaryName"].get("autoNumber") == "INS-{SEQNUM:5}"      # the app never builds an inspection number


def test_user_owned_tables_are_the_ones_the_field_inspector_role_scopes_to_own_records(schema):
    owned = {t["logicalName"] for t in schema["tables"] if t["ownership"] == "UserOwned"}
    role = next(r for r in schema["security"]["roles"] if r["name"] == "Inspection Field Inspector")["privileges"]
    for name in owned:
        for verb in ("Create", "Read", "Write", "Append", "AppendTo"):
            assert role[name][verb] == "Basic", (name, verb)
        assert "Delete" not in role[name]   # an inspector can't delete or reassign
    # Organization-owned tables can only be Global or none: Basic isn't meaningful there.
    for name in ("cin_site", "cin_inspector"):
        assert role[name]["Read"] == "Global"


def test_role_privileges_use_known_verbs_and_depths(schema):
    for role in schema["security"]["roles"]:
        for table, verbs in role["privileges"].items():
            assert table in tables(schema)
            for verb, depth in verbs.items():
                assert verb in ROLE_VERBS, verb
                assert depth in ROLE_DEPTHS, (role["name"], table, verb, depth)


def test_the_secured_column_is_the_one_the_field_security_profile_covers(schema):
    secured = {(t["logicalName"], c["logicalName"]) for t in schema["tables"] for c in t["columns"] if c.get("secured")}
    profiled = {(p["table"], p["column"]) for fsp in schema["security"]["fieldSecurityProfiles"] for p in fsp["permissions"]}
    assert secured == profiled == {("cin_inspection", "cin_reviewernotes")}


def test_sample_data_is_fictional_and_covers_the_demo(schema, seed):
    assert [i["name"] for i in seed["inspectors"]] == ["Alex Demo", "Sam Demo"]
    for i in seed["inspectors"]:
        assert i["defaultEmail"].endswith("@contoso.com")
        assert i["emailParameter"] in {"AlexEmail", "SamEmail"}
    risks = [o[0] for o in next(c for c in tables(schema)["cin_site"]["columns"] if c["logicalName"] == "cin_risklevel")["options"]]
    assert all(s["risk"] in risks for s in seed["sites"])
    assert len({s["code"] for s in seed["sites"]}) == len(seed["sites"]) == 3
    assert all(len(s["code"]) <= 20 and len(s["name"]) <= 100 for s in seed["sites"])


def test_the_seed_sites_are_the_ones_episode_12_loads():
    # Same codes and names as episode 12's CSV: loading both, in either order, never makes a duplicate site.
    csv = (CANONICAL_SCHEMA_PATH.parents[1] / "data" / "sites.csv").read_text(encoding="utf-8").splitlines()[1:]
    theirs = {line.split(",")[1]: line.split(",")[0] for line in csv}
    for s in json.loads(SEED_PATH.read_text(encoding="utf-8"))["sites"]:
        assert theirs.get(s["code"]) == s["name"], s["code"]


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
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    assert json.loads(raw)
    assert raw.endswith("\n")
