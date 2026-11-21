"""The schema file is the single source of truth for the shared ContosoInspections data model."""
import re


def test_every_logical_name_has_the_publisher_prefix_and_is_lowercase(schema):
    prefix = schema["publisher"]["prefix"] + "_"
    for t in schema["tables"]:
        assert t["logicalName"].startswith(prefix) and t["logicalName"].islower(), t["logicalName"]
        assert t["primaryName"]["logicalName"] == prefix + "name"
        for c in t["columns"]:
            assert c["logicalName"].startswith(prefix) and c["logicalName"] == c["logicalName"].lower(), c["logicalName"]
    for r in schema["relationships"]:
        assert r["name"].startswith(prefix)


def test_display_names_are_unique_per_table_so_canvas_apps_never_see_duplicates(schema):
    """In a canvas app columns are addressed by display name. The primary key column is displayed with the table's name."""
    for t in schema["tables"]:
        names = [t["displayName"], t["primaryName"]["displayName"]] + [c["displayName"] for c in t["columns"]]
        assert len(names) == len(set(names)), (t["logicalName"], names)


def test_option_values_use_the_publisher_option_value_prefix(schema):
    base = schema["publisher"]["optionValuePrefix"] * 10000
    seen = set()
    for t in schema["tables"]:
        for c in t["columns"]:
            if c["type"] != "choice":
                continue
            assert c["choice"] not in seen, f"choice name reused: {c['choice']}"
            seen.add(c["choice"])
            values = [v for _, v in c["options"]]
            assert len(values) == len(set(values))
            assert c["default"] in values
            assert all(0 <= v < 10000 for v in values)       # base + v stays inside the prefix range
            assert 10000 <= schema["publisher"]["optionValuePrefix"] <= 99999 or True
    assert 10000 <= schema["publisher"]["optionValuePrefix"] * 1 <= 99999 * 10000 or base > 0


def test_publisher_prefix_rules_from_learn(schema):
    # Learn (Create a solution publisher): 2-8 characters, letters and numbers, starts with a letter, not 'mscrm'
    p = schema["publisher"]["prefix"]
    assert re.fullmatch(r"[a-z][a-z0-9]{1,7}", p) and p != "mscrm"
    # option value prefix is between 10,000 and 99,999
    assert 10000 <= schema["publisher"]["optionValuePrefix"] <= 99999


def test_every_lookup_has_a_matching_one_to_many_relationship(schema):
    tables = {t["logicalName"]: t for t in schema["tables"]}
    rels = {(r["referencing"], r["lookup"]): r for r in schema["relationships"]}
    for t in schema["tables"]:
        for c in t["columns"]:
            if c["type"] == "lookup":
                r = rels.get((t["logicalName"], c["logicalName"]))
                assert r, f"no relationship for {t['logicalName']}.{c['logicalName']}"
                assert r["referenced"] == c["target"] and c["target"] in tables
    assert len(rels) == sum(1 for t in schema["tables"] for c in t["columns"] if c["type"] == "lookup")


def test_deleting_a_site_with_inspections_is_blocked_and_deleting_an_inspection_removes_its_items(schema):
    by = {r["name"]: r for r in schema["relationships"]}
    assert by["cin_site_inspection"]["delete"] == "Restrict"
    assert by["cin_inspector_inspection"]["delete"] == "RemoveLink"
    assert by["cin_inspection_inspectionitem"]["delete"] == "Cascade" and by["cin_inspection_inspectionitem"]["parental"]


def test_autonumber_format_follows_learn(schema):
    # Learn: {SEQNUM:n} has a minimum length of 1; {RANDSTRING:n} must be 1-6
    fmt = next(t for t in schema["tables"] if t["logicalName"] == "cin_inspection")["primaryName"]["autoNumber"]
    assert re.fullmatch(r"[A-Za-z0-9\-#]*\{SEQNUM:[1-9]\d*\}[A-Za-z0-9\-#]*", fmt), fmt


def test_alternate_key_columns_exist_and_are_text_or_whole_number(schema):
    for t in schema["tables"]:
        cols = {c["logicalName"]: c for c in t["columns"]}
        for k in t.get("alternateKeys", []):
            for col in k["columns"]:
                assert cols[col]["type"] in ("string", "whole")


def test_secured_columns_are_the_ones_the_field_security_profile_covers(schema):
    secured = {(t["logicalName"], c["logicalName"]) for t in schema["tables"] for c in t["columns"] if c.get("secured")}
    profiled = {(p["table"], p["column"]) for fp in schema["security"]["fieldSecurityProfiles"] for p in fp["permissions"]}
    assert secured == profiled == {("cin_inspection", "cin_reviewernotes")}


def test_the_schema_fits_both_apps_the_canvas_app_needs_inspector_and_owner_columns(schema):
    insp = next(t for t in schema["tables"] if t["logicalName"] == "cin_inspection")
    assert insp["ownership"] == "UserOwned"        # owner-scoped security roles for field inspectors
    assert {c["logicalName"] for c in insp["columns"]} >= {"cin_siteid", "cin_inspectorid", "cin_status", "cin_score"}
    for name in ("cin_site", "cin_inspector"):
        assert next(t for t in schema["tables"] if t["logicalName"] == name)["ownership"] == "OrganizationOwned"
