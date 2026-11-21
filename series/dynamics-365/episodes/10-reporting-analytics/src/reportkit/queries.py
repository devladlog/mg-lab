"""The same question asked three ways: FetchXML aggregate, OData $apply, and client-side rows.

Question: open opportunities (statecode 0), how many and how much (estimatedvalue), per group.
Learn (Aggregate data by using FetchXML / OData): aggregate queries are limited to 50,000 records; FetchXML can group by
a part of a date (`dategrouping`), OData `groupby` with datetime values isn't supported; grouping in FetchXML needs an
`order` with the alias of the group.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from .webapi import DataverseError, WebApi, odata_string

FMT = "@OData.Community.Display.V1.FormattedValue"
LIMIT = 50_000


@dataclass
class Group:
    count: int = 0
    total: float = 0.0
    label: str = ""


Report = Dict[Any, Group]


class AggregateLimit(Exception):
    """AggregateQueryRecordLimit (8004E023): more than 50,000 records match the filter."""


def fetch_by_column(by: str = "msdyn_forecastcategory") -> str:
    return (f'<fetch aggregate="true"><entity name="opportunity">'
            f'<attribute name="estimatedvalue" alias="total" aggregate="sum" />'
            f'<attribute name="opportunityid" alias="n" aggregate="count" />'
            f'<attribute name="{by}" alias="grp" groupby="true" />'
            f'<filter><condition attribute="statecode" operator="eq" value="0" /></filter>'
            f'<order alias="grp" /></entity></fetch>')


def fetch_by_month() -> str:
    return ('<fetch aggregate="true"><entity name="opportunity">'
            '<attribute name="estimatedvalue" alias="total" aggregate="sum" />'
            '<attribute name="opportunityid" alias="n" aggregate="count" />'
            '<attribute name="estimatedclosedate" alias="yr" groupby="true" dategrouping="year" usertimezone="false" />'
            '<attribute name="estimatedclosedate" alias="mo" groupby="true" dategrouping="month" usertimezone="false" />'
            '<filter><condition attribute="statecode" operator="eq" value="0" /></filter>'
            '<order alias="yr" /><order alias="mo" /></entity></fetch>')


def apply_by_column(by: str = "msdyn_forecastcategory") -> str:
    return (f"opportunities?$apply=filter(statecode eq 0)/groupby(({by}),"
            f"aggregate(estimatedvalue with sum as total,$count as n))")


def raw_rows(by: str) -> str:
    return f"opportunities?$select=estimatedvalue,estimatedclosedate,{by}&$filter=statecode eq 0"


def run_fetch(api: WebApi, fetch_xml: str) -> List[Dict[str, Any]]:
    try:
        return api.get(f"opportunities?fetchXml={quote(fetch_xml)}", annotations=True).get("value", [])
    except DataverseError as e:
        _raise_if_limit(e)
        raise


def run_apply(api: WebApi, path: str) -> List[Dict[str, Any]]:
    try:
        return api.get(path, annotations=True).get("value", [])
    except DataverseError as e:
        _raise_if_limit(e)
        raise


def _raise_if_limit(e: DataverseError) -> None:
    blob = f"{e.code} {e.message}".lower()
    if "aggregatequeryrecordlimit" in blob or "8004e023" in blob:
        raise AggregateLimit("more than 50,000 records match: add a filter (a date range or a subset of a choice "
                             "column), run the query several times and combine the results") from e


def _money(v: Any) -> float:
    return float(v) if v is not None else 0.0          # aggregate sums skip nulls, so a group of nulls has no total


def from_fetch_rows(rows: Iterable[Dict[str, Any]]) -> Report:
    out: Report = {}
    for r in rows:
        g = out.setdefault(r.get("grp"), Group())
        g.count, g.total, g.label = int(r.get("n") or 0), _money(r.get("total")), r.get("grp" + FMT, "")
    return out


def from_apply_rows(rows: Iterable[Dict[str, Any]], by: str) -> Report:
    out: Report = {}
    for r in rows:
        g = out.setdefault(r.get(by), Group())
        g.count, g.total, g.label = int(r.get("n") or 0), _money(r.get("total")), r.get(by + FMT, "")
    return out


def from_client_rows(rows: Iterable[Dict[str, Any]], by: str) -> Report:
    out: Report = {}
    for r in rows:
        g = out.setdefault(r.get(by), Group())
        g.count += 1
        g.total += _money(r.get("estimatedvalue"))
        g.label = g.label or r.get(by + FMT, "")
    return out


def month_key(date_text: Optional[str]) -> Optional[Tuple[int, int]]:
    if not date_text:
        return None
    y, m = date_text[:10].split("-")[:2]
    return int(y), int(m)


def from_fetch_month_rows(rows: Iterable[Dict[str, Any]]) -> Report:
    out: Report = {}
    for r in rows:
        key = (int(r["yr"]), int(r["mo"])) if r.get("yr") is not None and r.get("mo") is not None else None
        out[key] = Group(int(r.get("n") or 0), _money(r.get("total")))
    return out


def from_client_month_rows(rows: Iterable[Dict[str, Any]]) -> Report:
    out: Report = {}
    for r in rows:
        g = out.setdefault(month_key(r.get("estimatedclosedate")), Group())
        g.count += 1
        g.total += _money(r.get("estimatedvalue"))
    return out


def differences(reference: Report, other: Report, tol: float = 0.005) -> List[str]:
    msgs = []
    for key in sorted(set(reference) | set(other), key=lambda k: (k is None, str(k))):
        a, b = reference.get(key), other.get(key)
        if a is None or b is None:
            msgs.append(f"{key!s}: only in {'reference' if b is None else 'other'}")
        elif a.count != b.count or abs(a.total - b.total) > tol:
            msgs.append(f"{key!s}: {a.count} / {a.total:,.2f} vs {b.count} / {b.total:,.2f}")
    return msgs


def fmt_key(key: Any, g: Group) -> str:
    if isinstance(key, tuple):
        return f"{key[0]}-{key[1]:02d}"
    return g.label or ("(none)" if key is None else str(key))
