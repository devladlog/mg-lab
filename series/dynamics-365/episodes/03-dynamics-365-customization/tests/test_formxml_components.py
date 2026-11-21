import base64
import xml.etree.ElementTree as ET

import pytest

from conftest import FIXTURE_FORM
from custkit import components, formxml

LIB = "mgl_/projectrequest/form.js"
FN = "MGL.ProjectRequest.onLoad"


def handlers(xml):
    return ET.fromstring(xml).findall("./events/event[@name='onload']/Handlers/Handler")


def test_register_adds_library_and_onload_handler_with_execution_context():
    res = formxml.register_onload(FIXTURE_FORM, LIB, FN)
    assert res.changed and res.actions == [f"added library {LIB}", f"added OnLoad handler {FN}"]
    root = ET.fromstring(res.xml)
    lib = root.find("./formLibraries/Library")
    assert lib.get("name") == LIB and lib.get("libraryUniqueId").startswith("{")
    (h,) = handlers(res.xml)
    assert h.get("functionName") == FN and h.get("libraryName") == LIB
    assert h.get("passExecutionContext") == "true" and h.get("enabled") == "true"
    assert root.find("./events/event[@name='onload']").get("application") == "false"


def test_register_is_idempotent_and_ids_are_stable():
    once = formxml.register_onload(FIXTURE_FORM, LIB, FN)
    twice = formxml.register_onload(once.xml, LIB, FN)
    assert not twice.changed and twice.xml == once.xml
    again = formxml.register_onload(FIXTURE_FORM, LIB, FN)
    assert again.xml == once.xml          # same GUIDs on every machine -> no noisy diffs


def test_register_fixes_a_handler_without_execution_context():
    xml = formxml.register_onload(FIXTURE_FORM, LIB, FN).xml.replace('passExecutionContext="true"',
                                                                      'passExecutionContext="false"')
    res = formxml.register_onload(xml, LIB, FN)
    assert res.actions == [f"set passExecutionContext=true on {FN}"]
    assert handlers(res.xml)[0].get("passExecutionContext") == "true"


def test_register_keeps_existing_libraries_and_handlers():
    other = formxml.register_onload(FIXTURE_FORM, "mgl_/shared/common.js", "MGL.Common.onLoad").xml
    res = formxml.register_onload(other, LIB, FN)
    names = [lib.get("name") for lib in ET.fromstring(res.xml).iter("Library")]
    assert names == ["mgl_/shared/common.js", LIB]
    assert [h.get("functionName") for h in handlers(res.xml)] == ["MGL.Common.onLoad", FN]


def test_register_works_on_a_customizations_xml_systemform_wrapper():
    wrapped = f"<systemform><formid>{{00000000-0000-0000-0000-000000000000}}</formid>{FIXTURE_FORM}</systemform>"
    res = formxml.register_onload(wrapped, LIB, FN)
    assert ET.fromstring(res.xml).find("./form/formLibraries/Library") is not None


def test_unregister_removes_handler_and_empty_formlibraries():
    added = formxml.register_onload(FIXTURE_FORM, LIB, FN).xml
    res = formxml.unregister(added, LIB)
    assert res.changed
    root = ET.fromstring(res.xml)
    assert root.find("formLibraries") is None and not handlers(res.xml)
    assert not formxml.unregister(res.xml, LIB).changed


def test_missing_fields_reports_columns_not_on_the_form_including_header():
    assert formxml.fields_on_form(FIXTURE_FORM) >= {"mgl_name", "mgl_budget", "ownerid"}
    assert formxml.missing_fields(FIXTURE_FORM, ["mgl_budget", "mgl_justification", "ownerid"]) == ["mgl_justification"]


def test_form_xml_without_form_element_is_rejected():
    with pytest.raises(ValueError):
        formxml.register_onload("<systemform />", LIB, FN)


def test_justification_column_is_a_memo_textarea(cfg):
    col = components.justification_column(cfg)
    assert col["@odata.type"] == "Microsoft.Dynamics.CRM.MemoAttributeMetadata"
    assert col["AttributeType"] == "Memo" and col["Format"] == "TextArea" and col["MaxLength"] == 2000
    assert col["SchemaName"].startswith("mgl_") and col["RequiredLevel"]["Value"] == "None"


def test_webresource_payload_is_script_type_3_in_base64(cfg):
    body = components.webresource(cfg, b"var MGL;")
    assert body["webresourcetype"] == 3 and base64.b64decode(body["content"]) == b"var MGL;"
    assert body["name"] == "mgl_/projectrequest/form.js"


@pytest.mark.parametrize("name", ["projectrequest/form.js", "new_/form.js", "mgl_//form.js", "mgl_/form js.js",
                                  "mgl_/form.ts"])
def test_bad_webresource_names_are_refused(name):
    with pytest.raises(ValueError):
        components.validate_webresource_name(name, "mgl")


def test_empty_script_is_refused(cfg):
    with pytest.raises(ValueError, match="npm test"):
        components.webresource(cfg, b"  \n")


def test_view_is_public_with_real_object_type_code_and_consistent_columns(cfg):
    body = components.savedquery(cfg, 10234)
    assert body["querytype"] == 0 and body["returnedtypecode"] == "mgl_projectrequest"
    grid = ET.fromstring(body["layoutxml"])
    assert grid.get("object") == "10234" and grid.find("row").get("id") == "mgl_projectrequestid"
    fetch = ET.fromstring(body["fetchxml"])
    conds = {(c.get("attribute"), c.get("operator"), c.get("value")) for c in fetch.iter("condition")}
    assert conds == {("statecode", "eq", "0"), ("mgl_budget", "ge", "50000")}
    assert fetch.find(".//order").attrib == {"attribute": "mgl_budget", "descending": "true"}


def test_check_view_catches_a_cell_that_isnt_fetched(cfg):
    fetch = components.view_fetchxml(cfg).replace('<attribute name="mgl_duedate" />', "")
    with pytest.raises(ValueError, match="mgl_duedate"):
        components.check_view(fetch, components.view_layoutxml(cfg, 10234))


def test_publish_xml_table_and_braced_webresource_ids():
    assert components.publish_xml("mgl_projectrequest") == \
        "<importexportxml><entities><entity>mgl_projectrequest</entity></entities></importexportxml>"
    xml = components.publish_xml("mgl_projectrequest", ["aaaa"])
    assert "<webresources><webresource>{aaaa}</webresource></webresources>" in xml


def test_unregister_leaves_no_empty_events_element():
    # FormXml schema: <events> needs at least one <event>; an empty one would be invalid.
    res = formxml.unregister(formxml.register_onload(FIXTURE_FORM, LIB, FN).xml, LIB)
    assert ET.fromstring(res.xml).find("events") is None


def test_unregister_keeps_other_libraries_handlers():
    both = formxml.register_onload(formxml.register_onload(FIXTURE_FORM, "mgl_/shared/common.js",
                                                           "MGL.Common.onLoad").xml, LIB, FN).xml
    res = formxml.unregister(both, LIB)
    assert [h.get("functionName") for h in handlers(res.xml)] == ["MGL.Common.onLoad"]
    assert [lib.get("name") for lib in ET.fromstring(res.xml).iter("Library")] == ["mgl_/shared/common.js"]
