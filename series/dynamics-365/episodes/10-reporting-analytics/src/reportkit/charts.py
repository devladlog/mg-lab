"""Chart definitions as Dataverse rows (user-owned chart, `userqueryvisualization`).

Learn (Understand charts / Sample charts): a chart has a data description XML (`<fetchcollection>` with a FetchXML
aggregate query and `<categorycollection>` with one `<measurecollection>` per series) and a presentation description XML
(a serialization of the Microsoft Chart Controls `Chart` class; one `<Series>` per measure collection). Name: max 100.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from .webapi import WebApi, odata_string

NAME_MAX = 100
DEFAULT_PREFIX = "[MGL demo] "

_AXES = ('<ChartAreas><ChartArea BorderColor="White" BorderDashStyle="Solid">'
         '<AxisY LabelAutoFitMinFontSize="8" LineColor="165, 172, 181"><MajorGrid LineColor="239, 242, 246" /></AxisY>'
         '<AxisX LabelAutoFitMinFontSize="8" LineColor="165, 172, 181"><MajorGrid Enabled="False" />'
         '<MajorTickMark Enabled="False" /></AxisX></ChartArea></ChartAreas>')


def _series(chart_type: str, color: str, labels: bool) -> str:
    return (f'<Series ChartType="{chart_type}" IsValueShownAsLabel="{labels}" Color="{color}" Font="{{0}}, 9.5px" '
            f'LabelForeColor="59, 59, 59" CustomProperties="PointWidth=0.75, MaxPixelPointWidth=40">'
            f'<SmartLabelStyle Enabled="True" /></Series>')


def pipeline_by_category() -> Dict[str, str]:
    data = ('<datadefinition><fetchcollection><fetch mapping="logical" aggregate="true"><entity name="opportunity">'
            '<attribute name="estimatedvalue" aggregate="sum" alias="sum_estimatedvalue" />'
            '<attribute name="msdyn_forecastcategory" groupby="true" alias="groupby_column" />'
            '<filter><condition attribute="statecode" operator="eq" value="0" /></filter>'
            '</entity></fetch></fetchcollection><categorycollection><category><measurecollection>'
            '<measure alias="sum_estimatedvalue" /></measurecollection></category></categorycollection></datadefinition>')
    pres = f'<Chart><Series>{_series("Column", "91, 151, 213", True)}</Series>{_AXES}</Chart>'
    return {"name": "Open pipeline by forecast category", "entity": "opportunity", "data": data, "presentation": pres}


def estimated_vs_actual_by_month() -> Dict[str, str]:
    data = ('<datadefinition><fetchcollection><fetch mapping="logical" aggregate="true"><entity name="opportunity">'
            '<attribute name="estimatedvalue" aggregate="sum" alias="estvalue" />'
            '<attribute name="actualvalue" aggregate="sum" alias="actvalue" />'
            '<attribute name="actualclosedate" groupby="true" alias="actclosedate" dategrouping="month" />'
            '</entity></fetch></fetchcollection><categorycollection><category>'
            '<measurecollection><measure alias="estvalue" /></measurecollection>'
            '<measurecollection><measure alias="actvalue" /></measurecollection>'
            '</category></categorycollection></datadefinition>')
    pres = (f'<Chart><Series>{_series("Column", "91, 151, 213", False)}{_series("Column", "237, 125, 49", False)}'
            f'</Series>{_AXES}<Legends><Legend Alignment="Center" LegendStyle="Table" Docking="Bottom" />'
            f'</Legends></Chart>')
    return {"name": "Estimated vs actual revenue by month", "entity": "opportunity", "data": data, "presentation": pres}


BUILDERS = {"pipeline": pipeline_by_category, "revenue": estimated_vs_actual_by_month}


def validate(spec: Dict[str, str]) -> List[str]:
    """Structural checks of what Learn documents; returns problems (empty = fine)."""
    problems: List[str] = []
    name = spec["name"]
    if len(DEFAULT_PREFIX + name) > NAME_MAX:
        problems.append(f"name is {len(DEFAULT_PREFIX + name)} characters, the column allows {NAME_MAX}")
    try:
        data, pres = ET.fromstring(spec["data"]), ET.fromstring(spec["presentation"])
    except ET.ParseError as e:
        return problems + [f"not well-formed XML: {e}"]
    fetch = data.find("./fetchcollection/fetch")
    if fetch is None:
        return problems + ["data description has no <fetchcollection><fetch>"]
    if fetch.get("aggregate") != "true":
        problems.append("fetch must have aggregate=\"true\"")
    aliases = {a.get("alias") for a in fetch.iter("attribute") if a.get("alias")}
    collections = data.findall("./categorycollection/category/measurecollection")
    if not collections:
        problems.append("no <measurecollection> in the category collection")
    for mc in collections:
        for m in mc.findall("measure"):
            if m.get("alias") not in aliases:
                problems.append(f"measure '{m.get('alias')}' is not an attribute alias in the fetch")
    series = pres.findall("./Series/Series")
    if len(series) != len(collections):
        problems.append(f"{len(series)} <Series> in the presentation but {len(collections)} <measurecollection> "
                        "in the data description (Learn: they map one to one)")
    if not any(a.get("groupby") == "true" for a in fetch.iter("attribute")):
        problems.append("no groupby attribute: the chart would have a single point")
    return problems


def body(spec: Dict[str, str], prefix: str = DEFAULT_PREFIX) -> Dict[str, Any]:
    return {"name": prefix + spec["name"], "primaryentitytypecode": spec["entity"], "charttype": 0,
            "isdefault": False, "description": "Created by reportkit (DEVLADLOG Dynamics 365 episode 10)",
            "datadescription": spec["data"], "presentationdescription": spec["presentation"]}


def create(api: WebApi, spec: Dict[str, str], *, apply: bool, out=print) -> str:
    problems = validate(spec)
    if problems:
        raise ValueError("chart definition is invalid: " + "; ".join(problems))
    b = body(spec)
    existing = list(api.get_all(f"userqueryvisualizations?$select=userqueryvisualizationid&$filter=name eq "
                                f"{odata_string(b['name'])}"))
    if existing:
        out(f"= {b['name']} (already exists)")
        return existing[0]["userqueryvisualizationid"]
    if not apply:
        out(f"+ {b['name']} (dry run)")
        return ""
    r = api.post("userqueryvisualizations", b)
    url = r.headers.get("OData-EntityId", "")
    out(f"+ {b['name']} created")
    return url.rsplit("(", 1)[-1].rstrip(")") if "(" in url else ""
