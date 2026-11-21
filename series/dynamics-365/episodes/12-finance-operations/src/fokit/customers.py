"""Read customers from finance and operations (Customers V3) and accounts from Dataverse, as plain records.

Learn (dual-write): in the Customers V3 (accounts) map CustomerAccount is mapped to accountnumber, and the source
filter is PartyType == Organization (people go to the Customers V3 (contacts) map). Customers V3 is company-specific:
the same CustomerAccount can exist in several legal entities (dataAreaId).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .dataverse import DataverseApi
from .fo import FoApi, odata_string


@dataclass(frozen=True)
class FoCustomer:
    account: str
    company: str
    name: str
    party_type: str
    group: str


@dataclass(frozen=True)
class DvAccount:
    number: str
    name: str


def fo_url(api: FoApi, cfg: Dict[str, Any], company: Optional[str] = None, top: Optional[int] = None) -> str:
    flt = f"dataAreaId eq {odata_string(company)}" if company else None
    return api.url(cfg["entity"], select=cfg["select"], filter=flt, top=top, cross_company=True)


def to_customer(row: Dict[str, Any]) -> FoCustomer:
    return FoCustomer((row.get("CustomerAccount") or "").strip(), row.get("dataAreaId") or "",
                      (row.get("OrganizationName") or "").strip(), str(row.get("PartyType") or ""),
                      row.get("CustomerGroupId") or "")


def fetch_customers(api: FoApi, cfg: Dict[str, Any], company: Optional[str] = None) -> List[FoCustomer]:
    return [to_customer(r) for r in api.get_all(fo_url(api, cfg, company))]


def dv_query(cfg: Dict[str, Any]) -> str:
    return f"{cfg['dataverse_table']}?$select=accountnumber,name&$filter=accountnumber ne null"


def to_account(row: Dict[str, Any]) -> DvAccount:
    return DvAccount((row.get("accountnumber") or "").strip(), (row.get("name") or "").strip())


def fetch_accounts(api: DataverseApi, cfg: Dict[str, Any]) -> List[DvAccount]:
    return [to_account(r) for r in api.get_all(dv_query(cfg))]
