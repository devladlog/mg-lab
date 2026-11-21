"""Payloads for the components episode 3 adds, all pure functions (no network):

- the Business Justification column (MemoAttributeMetadata),
- the form script web resource (webresource row, type 3 = Script (JScript), content in Base64),
- the "Open requests over 50,000" public view (savedquery row: fetchxml + layoutxml, querytype 0).
"""
from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Sequence
from xml.sax.saxutils import quoteattr

LCID = 1033
ODATA = "Microsoft.Dynamics.CRM."
WEBRESOURCE_SCRIPT = 3      # webresourcetype: 3 = Script (JScript)
VIEW_PUBLIC = 0             # savedquery.querytype: must be 0 for a public view you create

# Learn (web resources): names use the publisher prefix and can contain '/' to build virtual folders.
_WR_NAME = re.compile(r"^[A-Za-z0-9]+_/?(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\.js$")


def label(text: str) -> Dict[str, Any]:
    return {"@odata.type": ODATA + "Label",
            "LocalizedLabels": [{"@odata.type": ODATA + "LocalizedLabel", "Label": text, "LanguageCode": LCID}]}


def justification_column(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """POST EntityDefinitions(LogicalName='<table>')/Attributes. Optional at the column level on purpose:
    the business rule decides when it's needed."""
    col = cfg["column"]
    return {
        "@odata.type": ODATA + "MemoAttributeMetadata",
        "AttributeType": "Memo",
        "AttributeTypeName": {"Value": "MemoType"},
        "SchemaName": col["schema_name"],
        "DisplayName": label(col["display_name"]),
        "Description": label(col["description"]),
        "RequiredLevel": {"Value": "None", "CanBeChanged": True,
                          "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings"},
        "Format": "TextArea",
        "MaxLength": col["max_length"],
    }


def validate_webresource_name(name: str, prefix: str) -> None:
    if not name.startswith(prefix + "_"):
        raise ValueError(f"web resource name {name!r} must start with the publisher prefix '{prefix}_'")
    if "//" in name or not _WR_NAME.match(name):
        raise ValueError(f"web resource name {name!r}: letters, digits, '_', '-', '.', single '/' only, ending in .js")


def webresource(cfg: Dict[str, Any], script: bytes) -> Dict[str, Any]:
    wr = cfg["webresource"]
    validate_webresource_name(wr["name"], cfg["publisher_prefix"])
    if not script.strip():
        raise ValueError("the compiled script is empty: run `npm test` in formscript/ first")
    return {
        "name": wr["name"],
        "displayname": wr["display_name"],
        "webresourcetype": WEBRESOURCE_SCRIPT,
        "content": base64.b64encode(script).decode("ascii"),
    }


def view_fetchxml(cfg: Dict[str, Any]) -> str:
    v, table = cfg["view"], cfg["table"]
    attrs = "".join(f"<attribute name={quoteattr(c)} />" for c, _ in v["columns"])
    return (f"<fetch version=\"1.0\" mapping=\"logical\">"
            f"<entity name={quoteattr(table)}>"
            f"<attribute name=\"{table}id\" />{attrs}"
            f"<order attribute=\"mgl_budget\" descending=\"true\" />"
            f"<filter type=\"and\">"
            f"<condition attribute=\"statecode\" operator=\"eq\" value=\"0\" />"
            f"<condition attribute=\"mgl_budget\" operator=\"ge\" value=\"{int(v['threshold'])}\" />"
            f"</filter></entity></fetch>")


def view_layoutxml(cfg: Dict[str, Any], object_type_code: int) -> str:
    """`object` is the table's ObjectTypeCode. For custom tables it's assigned per environment, so it must be
    read from EntityDefinitions, never hard-coded (Learn's example uses 3 because that's opportunity)."""
    table = cfg["table"]
    cells = "".join(f"<cell name={quoteattr(c)} width=\"{int(w)}\" />" for c, w in cfg["view"]["columns"])
    return (f"<grid name=\"resultset\" object=\"{int(object_type_code)}\" jump=\"mgl_name\" select=\"1\" "
            f"icon=\"1\" preview=\"1\"><row name=\"result\" id=\"{table}id\">{cells}</row></grid>")


def savedquery(cfg: Dict[str, Any], object_type_code: int) -> Dict[str, Any]:
    body = {
        "name": cfg["view"]["name"],
        "description": cfg["view"]["description"],
        "returnedtypecode": cfg["table"],
        "querytype": VIEW_PUBLIC,
        "fetchxml": view_fetchxml(cfg),
        "layoutxml": view_layoutxml(cfg, object_type_code),
    }
    check_view(body["fetchxml"], body["layoutxml"])
    return body


def check_view(fetchxml: str, layoutxml: str) -> None:
    """Every column shown in the grid must be fetched, or it renders empty."""
    fetched = {a.get("name") for a in ET.fromstring(fetchxml).iter("attribute")}
    shown = [c.get("name") for c in ET.fromstring(layoutxml).iter("cell")]
    missing = [c for c in shown if c not in fetched]
    if missing:
        raise ValueError(f"layoutxml shows columns the fetchxml doesn't retrieve: {missing}")


def publish_xml(table: str, webresource_ids: Sequence[str] = ()) -> str:
    """ParameterXml for PublishXml: the table (form + view) and, when updated, the web resource."""
    wrs = "".join(f"<webresource>{{{i.strip('{}')}}}</webresource>" for i in webresource_ids)
    xml = f"<importexportxml><entities><entity>{table}</entity></entities>"
    if wrs:
        xml += f"<webresources>{wrs}</webresources>"
    return xml + "</importexportxml>"

