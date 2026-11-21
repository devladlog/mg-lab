"""Read companies, customers and sales invoices from Business Central, and accounts from Dataverse, as plain records.

Learn (customer resource type): number, displayName, type ('Company' or 'Person'), currencyCode, blocked (' ', 'Ship',
'Invoice' or 'All'). Learn (salesInvoice resource type): number, customerNumber, invoiceDate, dueDate, status (' ',
'Draft', 'In Review', 'Open', 'Paid', 'Canceled', 'Corrective'), totalAmountIncludingTax, remainingAmount. Everything
lives under companies({id}), and a customer number is only unique inside one company.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .bc import BcApi, BcError, odata_string
from .dataverse import DataverseApi


@dataclass(frozen=True)
class BcCustomer:
    number: str
    company: str
    name: str
    type: str
    currency: str = ""
    blocked: str = ""


@dataclass(frozen=True)
class BcInvoice:
    number: str
    company: str
    customer_number: str
    customer_name: str
    invoice_date: str
    due_date: str
    status: str
    currency: str
    total: float
    remaining: float


@dataclass(frozen=True)
class DvAccount:
    number: str
    name: str


def fetch_companies(api: BcApi) -> List[Dict[str, Any]]:
    return list(api.get_all(api.companies_url()))


def pick_companies(companies: List[Dict[str, Any]], wanted: Optional[str]) -> List[Dict[str, Any]]:
    """All companies, or the one whose name or displayName matches (case ignored). Unknown name: say which exist."""
    if not wanted:
        return companies
    hit = [c for c in companies if wanted.casefold() in {str(c.get("name", "")).casefold(), str(c.get("displayName", "")).casefold()}]
    if not hit:
        names = ", ".join(repr(c.get("name")) for c in companies) or "none"
        raise BcError(0, f"no company named {wanted!r}; companies: {names}")
    return hit


def to_customer(row: Dict[str, Any], company: str) -> BcCustomer:
    return BcCustomer((row.get("number") or "").strip(), company, (row.get("displayName") or "").strip(),
                      str(row.get("type") or ""), row.get("currencyCode") or "", (row.get("blocked") or "").strip())


def fetch_customers(api: BcApi, cfg: Dict[str, Any], company: Optional[str] = None) -> List[BcCustomer]:
    out: List[BcCustomer] = []
    for c in pick_companies(fetch_companies(api), company):
        url = api.url(c["id"], "customers", select=cfg["customer_select"])
        out += [to_customer(r, c.get("name", "")) for r in api.get_all(url)]
    return out


def to_invoice(row: Dict[str, Any], company: str) -> BcInvoice:
    return BcInvoice((row.get("number") or "").strip(), company, (row.get("customerNumber") or "").strip(),
                     (row.get("customerName") or "").strip(), row.get("invoiceDate") or "", row.get("dueDate") or "",
                     (row.get("status") or "").strip(), row.get("currencyCode") or "",
                     float(row.get("totalAmountIncludingTax") or 0), float(row.get("remainingAmount") or 0))


def fetch_invoices(api: BcApi, cfg: Dict[str, Any], company: Optional[str] = None, status: Optional[str] = None,
                   customer: Optional[str] = None, top: Optional[int] = None) -> List[BcInvoice]:
    flt = " and ".join(f for f in [f"status eq {odata_string(status)}" if status else "",
                                   f"customerNumber eq {odata_string(customer)}" if customer else ""] if f) or None
    out: List[BcInvoice] = []
    for c in pick_companies(fetch_companies(api), company):
        url = api.url(c["id"], "salesInvoices", select=cfg["invoice_select"], filter=flt,
                      orderby="invoiceDate desc", top=top)
        out += [to_invoice(r, c.get("name", "")) for r in api.get_all(url)]
    return out


def seed_customers(api: BcApi, cfg: Dict[str, Any], company: str, dry_run: bool = False) -> List[str]:
    """Create the fictional demo customers in one company; skip a display name that already exists. Returns log lines.
    Business Central assigns the number (Learn's create example returns it): read it from the output."""
    (c,) = pick_companies(fetch_companies(api), company)
    log: List[str] = []
    for spec in cfg["seed_customers"]:
        name = spec["displayName"]
        existing = list(api.get_all(api.url(c["id"], "customers", select=["number", "displayName"],
                                            filter=f"displayName eq {odata_string(name)}")))
        if existing:
            log.append(f"exists   {existing[0].get('number', '?'):10} {name}")
        elif dry_run:
            log.append(f"would create {name} ({spec.get('type', 'Company')})")
        else:
            made = api.request("POST", api.url(c["id"], "customers"), body=spec) or {}
            log.append(f"created  {made.get('number', '?'):10} {name}")
    return log


def dv_query(cfg: Dict[str, Any]) -> str:
    return f"{cfg['dataverse_table']}?$select=accountnumber,name&$filter=accountnumber ne null"


def to_account(row: Dict[str, Any]) -> DvAccount:
    return DvAccount((row.get("accountnumber") or "").strip(), (row.get("name") or "").strip())


def fetch_accounts(api: DataverseApi, cfg: Dict[str, Any]) -> List[DvAccount]:
    return [to_account(r) for r in api.get_all(dv_query(cfg))]
