"""Checks on src/solution: the committed solution source, generated from the schema and unpacked by pac."""
import re
import xml.etree.ElementTree as ET

import pytest

from conftest import SOLUTION, has_pac

pytestmark = pytest.mark.skipif(not has_pac(), reason="pac CLI not installed")


def parse(path):
    return ET.fromstring(path.read_text(encoding="utf-8-sig"))


def all_xml():
    return sorted(p for p in SOLUTION.rglob("*.xml"))


def entity(table):
    return parse(SOLUTION / "Entities" / table / "Entity.xml")


def attributes(table):
    root = entity(table)
    return {a.findtext("LogicalName"): a for a in root.iter("attribute")}


def ids_in(folder):
    return {p.stem.upper() for p in (SOLUTION / folder).glob("*.xml")}


def guid_set(text):
    return set(g.upper() for g in re.findall(r"\{[0-9A-Fa-f-]{36}\}", text))


def test_every_xml_file_is_well_formed():
    assert len(all_xml()) >= 30
    for p in all_xml():
        parse(p)


def test_committed_source_equals_what_the_schema_generates_now(fresh_full):
    """If this fails, someone edited the schema or the generator without re-running build_solution.py (or edited the source by hand)."""
    mine = sorted(p.relative_to(SOLUTION).as_posix() for p in SOLUTION.rglob("*") if p.is_file())
    theirs = sorted(p.relative_to(fresh_full).as_posix() for p in fresh_full.rglob("*") if p.is_file())
    assert mine == theirs
    for rel in mine:
        assert (fresh_full / rel).read_bytes() == (SOLUTION / rel).read_bytes(), rel


def test_solution_manifest(schema):
    root = parse(SOLUTION / "Other" / "Solution.xml")
    m = root.find("SolutionManifest")
    assert m.findtext("UniqueName") == "ContosoInspections"
    assert m.findtext("Version") == schema["version"]
    assert m.findtext("Managed") == "0"
    pub = m.find("Publisher")
    assert pub.findtext("UniqueName") == "contosolab"
    assert pub.findtext("CustomizationPrefix") == "cin"
    assert pub.findtext("CustomizationOptionValuePrefix") == "45532"


def test_all_four_tables_and_their_columns_are_in_the_source(schema):
    for t in schema["tables"]:
        attrs = attributes(t["logicalName"])
        expected = {t["primaryName"]["logicalName"], f"{t['logicalName']}id"} | {c["logicalName"] for c in t["columns"]}
        assert expected <= set(attrs), (t["logicalName"], expected - set(attrs))


def test_ownership_matches_the_schema(schema):
    for t in schema["tables"]:
        want = "UserOwned" if t["ownership"] == "UserOwned" else "OrgOwned"
        assert entity(t["logicalName"]).find(".//OwnershipTypeMask").text == want


def test_the_secured_column_is_marked_secured_and_nothing_else_is(schema):
    secured = {(t["logicalName"], n) for t in schema["tables"] for n, a in attributes(t["logicalName"]).items() if a.findtext("IsSecured") == "1"}
    assert secured == {("cin_inspection", "cin_reviewernotes")}


def test_status_choice_has_the_five_values_with_the_publisher_prefix():
    status = attributes("cin_inspection")["cin_status"]
    opts = {o.find("labels/label").get("description"): int(o.get("value")) for o in status.iter("option")}
    assert opts == {"Draft": 455320000, "In progress": 455320001, "Submitted": 455320002, "Approved": 455320003, "Rejected": 455320004}
    assert status.findtext("DefaultFormValue") == "455320000"


def test_autonumber_on_the_inspection_name():
    assert attributes("cin_inspection")["cin_name"].findtext("AutoNumberFormat") == "INS-{SEQNUM:5}"


def test_score_is_limited_to_0_to_100():
    score = attributes("cin_inspection")["cin_score"]
    assert (score.findtext("MinValue"), score.findtext("MaxValue")) == ("0", "100")


def test_dates_are_date_only_so_time_zones_cannot_move_them():
    for table, col in (("cin_inspection", "cin_inspectiondate"), ("cin_site", "cin_lastinspectedon"), ("cin_inspectionitem", "cin_resolvedon")):
        a = attributes(table)[col]
        assert a.findtext("Behavior") == "3" and a.findtext("Format") == "date"


def test_relationships_are_in_the_source(schema):
    text = "".join(p.read_text(encoding="utf-8-sig") for p in (SOLUTION / "Other" / "Relationships").glob("*.xml"))
    for r in schema["relationships"]:
        assert f'<EntityRelationship Name="{r["name"]}">' in text
    assert "<CascadeDelete>Restrict</CascadeDelete>" in text and "<CascadeDelete>Cascade</CascadeDelete>" in text


def test_every_table_has_a_main_form_and_the_two_creatable_ones_have_quick_create(schema):
    for t in schema["tables"]:
        assert list((SOLUTION / "Entities" / t["logicalName"] / "FormXml" / "main").glob("*.xml")), t["logicalName"]
    for t in ("cin_inspection", "cin_inspectionitem"):
        assert list((SOLUTION / "Entities" / t / "FormXml" / "quick").glob("*.xml"))
        assert entity(t).findtext(".//IsQuickCreateEnabled") == "1"


def test_every_control_on_every_form_is_bound_to_a_column_of_that_table(schema):
    for t in schema["tables"]:
        attrs = set(attributes(t["logicalName"])) | {"ownerid"}
        for kind in ("main", "quick"):
            for p in (SOLUTION / "Entities" / t["logicalName"] / "FormXml" / kind).glob("*.xml") if (SOLUTION / "Entities" / t["logicalName"] / "FormXml" / kind).exists() else []:
                for c in parse(p).iter("control"):
                    if c.get("datafieldname"):
                        assert c.get("datafieldname") in attrs, (t["logicalName"], kind, c.get("datafieldname"))


def test_form_ids_and_control_ids_are_unique_within_a_form():
    for p in (SOLUTION / "Entities").rglob("FormXml/*/*.xml"):
        root = parse(p)
        cell_ids = [c.get("id") for c in root.iter("cell")]
        assert len(cell_ids) == len(set(cell_ids)), p
        ctl = [c.get("id") for c in root.iter("control")]
        assert len(ctl) == len(set(ctl)), p


def test_subgrids_point_at_views_that_exist_and_at_real_relationships(schema, model):
    rels = {r["name"] for r in schema["relationships"]}
    views = set()
    for p in (SOLUTION / "Entities").rglob("SavedQueries/*.xml"):
        views.add(p.stem.upper())
    found = 0
    for p in (SOLUTION / "Entities").rglob("FormXml/main/*.xml"):
        for c in parse(p).iter("control"):
            if c.get("classid", "").upper() == "{E7A81278-8635-4D9E-8D4D-59480B391C5B}":
                found += 1
                assert c.findtext("parameters/ViewId").upper() in views
                assert c.findtext("parameters/RelationshipName") in rels
    assert found == 2   # Site > Inspections and Inspection > Items


def test_views_select_only_columns_that_exist(schema):
    for t in schema["tables"]:
        attrs = set(attributes(t["logicalName"])) | {"createdon", "statecode", "ownerid", "modifiedon"}
        for p in (SOLUTION / "Entities" / t["logicalName"] / "SavedQueries").glob("*.xml"):
            root = parse(p)
            for node in root.iter("attribute"):
                assert node.get("name") in attrs, (p.name, node.get("name"))
            for cell in root.iter("cell"):
                assert cell.get("name") in attrs
            for cond in root.iter("condition"):
                assert cond.get("attribute") in attrs


def test_each_table_has_exactly_one_default_public_view_and_a_quick_find(schema):
    for t in schema["tables"]:
        qs = [parse(p).find("savedquery") for p in (SOLUTION / "Entities" / t["logicalName"] / "SavedQueries").glob("*.xml")]
        assert sum(q.findtext("isdefault") == "1" and q.findtext("querytype") == "0" for q in qs) == 1
        assert sum(q.findtext("querytype") == "4" for q in qs) == 1


def test_views_filter_on_choice_values_not_labels(schema):
    to_review = next(p for p in (SOLUTION / "Entities" / "cin_inspection" / "SavedQueries").glob("*.xml")
                     if "Inspections to review" in p.read_text(encoding="utf-8-sig"))
    cond = [c for c in parse(to_review).iter("condition") if c.get("attribute") == "cin_status"][0]
    assert cond.get("value") == "455320002"         # Submitted


def test_charts_group_by_a_real_column():
    for table, cat in (("cin_inspection", "cin_status"), ("cin_inspectionitem", "cin_severity")):
        (p,) = (SOLUTION / "Entities" / table / "Visualizations").glob("*.xml")
        root = parse(p)
        grp = [a for a in root.iter("attribute") if a.get("groupby") == "true"]
        assert [a.get("name") for a in grp] == [cat]
        assert root.find(".//attribute[@aggregate='count']") is not None


def test_dashboard_has_at_most_six_components_and_they_reference_existing_views_and_charts():
    """Learn: up to six components can be included in a dashboard."""
    (p,) = (SOLUTION / "Dashboards").glob("*.xml")
    root = parse(p)
    controls = list(root.iter("control"))
    assert 1 <= len(controls) <= 6
    views = {v.stem.upper() for v in (SOLUTION / "Entities").rglob("SavedQueries/*.xml")}
    charts = {v.stem.upper() for v in (SOLUTION / "Entities").rglob("Visualizations/*.xml")}
    for c in controls:
        assert c.findtext("parameters/ViewId").upper() in views
        vis = c.findtext("parameters/VisualizationId")
        if c.findtext("parameters/ChartGridMode") == "Chart":
            assert vis.upper() in charts
    assert root.findtext("FormId").upper().strip("{}") == p.stem.upper().strip("{}")


def test_site_map_points_at_the_dashboard_and_real_tables(schema, model):
    sm = parse(next((SOLUTION / "AppModuleSiteMaps").glob("*/AppModuleSiteMap.xml")))
    tables = {t["logicalName"] for t in schema["tables"]}
    subs = list(sm.iter("SubArea"))
    assert {s.get("Entity") for s in subs if s.get("Entity")} == tables
    dash = [s for s in subs if s.get("Url")]
    assert len(dash) == 1 and model.dashboard_id.strip("{}").lower() in dash[0].get("Url")
    assert len({s.get("Id") for s in subs}) == len(subs)


def test_app_module_lists_tables_site_map_and_is_limited_to_the_back_office_role(schema, model):
    app = parse(next((SOLUTION / "AppModules").glob("*/AppModule.xml")))
    assert app.findtext("UniqueName") == "cin_InspectionBackOffice"
    comps = [(c.get("type"), c.get("schemaName") or c.get("id")) for c in app.iter("AppModuleComponent")]
    assert {c for t, c in comps if t == "1"} == {t["logicalName"] for t in schema["tables"]}
    assert ("62", model.sitemap_id) in comps
    roles = [r.get("id") for r in app.iter("Role")]
    assert roles == [model.role_id("Inspection Back Office")]       # not the field inspector role: they use the canvas app


def test_every_app_component_id_exists_in_the_source(model):
    existing = ids_in("Dashboards") | {p.stem.upper() for p in (SOLUTION / "Entities").rglob("*/*.xml") if p.stem.startswith("{")}
    app = parse(next((SOLUTION / "AppModules").glob("*/AppModule.xml")))
    for c in app.iter("AppModuleComponent"):
        if c.get("type") in ("26", "59", "60"):
            assert c.get("id").upper() in existing, c.attrib


def test_root_components_cover_every_top_level_piece():
    root = parse(SOLUTION / "Other" / "Solution.xml")
    types = [(r.get("type")) for r in root.iter("RootComponent")]
    assert types.count("1") == 4 and types.count("20") == 2
    for t in ("60", "62", "70", "80"):
        assert types.count(t) == 1


def test_role_privileges_name_real_tables_and_valid_levels(schema):
    tables = {t["logicalName"]: t for t in schema["tables"]}
    for p in (SOLUTION / "Roles").glob("*.xml"):
        for rp in parse(p).iter("RolePrivilege"):
            m = re.fullmatch(r"prv(Create|Read|Write|Delete|Append|AppendTo|Assign|Share)(cin_\w+)", rp.get("name"))
            assert m and m.group(2) in tables, rp.attrib
            assert rp.get("level") in ("Basic", "Local", "Deep", "Global")
            if tables[m.group(2)]["ownership"] == "OrganizationOwned":
                # org-owned tables have no owner: Assign/Share don't exist and the only useful depth is organization
                assert m.group(1) not in ("Assign", "Share") and rp.get("level") == "Global"


def roles_by_name():
    out = {}
    for p in (SOLUTION / "Roles").glob("*.xml"):
        r = parse(p)
        out[r.findtext("Name")] = {rp.get("name"): rp.get("level") for rp in r.iter("RolePrivilege")}
    return out


def test_field_inspector_can_work_on_own_records_but_never_delete_or_reassign():
    fi = roles_by_name()["Inspection Field Inspector"]
    for t in ("cin_inspection", "cin_inspectionitem"):
        assert fi[f"prvCreate{t}"] == fi[f"prvRead{t}"] == fi[f"prvWrite{t}"] == "Basic"
        for op in ("Delete", "Assign", "Share"):
            assert f"prv{op}{t}" not in fi
    for t in ("cin_site", "cin_inspector"):
        assert fi[f"prvRead{t}"] == "Global"
        assert f"prvWrite{t}" not in fi and f"prvCreate{t}" not in fi


def test_back_office_reads_everything_across_the_organisation_and_can_delete():
    bo = roles_by_name()["Inspection Back Office"]
    for t in ("cin_inspection", "cin_inspectionitem", "cin_site", "cin_inspector"):
        assert bo[f"prvRead{t}"] == bo[f"prvWrite{t}"] == bo[f"prvDelete{t}"] == "Global"
    assert bo["prvAssigncin_inspection"] == "Global"


def test_lookups_need_append_to_on_the_target_and_append_on_the_source(schema):
    """Learn: to set a lookup you need Append on the table that holds it and Append To on the table it points at."""
    for rname, role in roles_by_name().items():
        for r in schema["relationships"]:
            src, dst = r["referencing"], r["referenced"]
            if f"prvCreate{src}" in role or f"prvWrite{src}" in role:
                assert f"prvAppend{src}" in role, (rname, src)
                assert f"prvAppendTo{dst}" in role, (rname, dst)


def test_field_security_profile_covers_the_secured_column():
    text = (SOLUTION / "Other" / "FieldSecurityProfiles.xml").read_text(encoding="utf-8-sig")
    assert 'entityname="cin_inspection" attributelogicalname="cin_reviewernotes"' in text
    assert 'canread="4"' in text   # Learn: 4 = Allowed, 0 = Not Allowed


def test_deterministic_guids_never_collide(model):
    ids = []
    for p in all_xml():
        ids += re.findall(r'(?:Id|id|formid|FormId|savedqueryid|savedqueryvisualizationid)(?:="|>)(\{[0-9A-F-]{36}\})', p.read_text(encoding="utf-8-sig"))
    assert len(ids) > 20
    cells = [i for p in (SOLUTION / "Entities").rglob("FormXml/*/*.xml") for i in re.findall(r'<cell id="(\{[0-9A-F-]{36}\})"', p.read_text(encoding="utf-8-sig"))]
    assert len(cells) == len(set(cells))
