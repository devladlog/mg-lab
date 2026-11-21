"""Compare customers in Business Central with accounts in Dataverse, by customer number = account number.

Business Central has no dual-write with Dataverse in this lab; the reconcile is the same check a dual-write setup (or any
sync) needs before it runs, and afterwards as a drift check. The key is the customer number on one side and
accountnumber on the other.

R001 error    Business Central company customer with no Dataverse account carrying that accountnumber
R002 warning  Dataverse account with an accountnumber that is not a Business Central customer
R003 warning  same number on both sides but the names differ (case and spacing ignored)
R004 warning  the same customer number exists in more than one Business Central company
R005 info     customers of type Person are left out: they are contacts, not accounts
R006 info     customer is blocked in Business Central (Ship, Invoice or All) but exists as an account
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from .customers import BcCustomer, DvAccount
from .findings import Finding


def norm(s: str) -> str:
    return " ".join(s.casefold().split())


def in_scope(text: str, contains: Optional[str]) -> bool:
    return not contains or contains.casefold() in text.casefold()


def reconcile(bc: List[BcCustomer], dv: List[DvAccount], company_type: str = "Company") -> List[Finding]:
    out: List[Finding] = []
    orgs = [c for c in bc if c.type == company_type]
    people = [c for c in bc if c.type != company_type]
    dv_by_number: Dict[str, List[DvAccount]] = defaultdict(list)
    for a in dv:
        dv_by_number[a.number].append(a)
    companies: Dict[str, List[str]] = defaultdict(list)
    for c in orgs:
        companies[c.number].append(c.company)

    for number in sorted(companies):
        where = ", ".join(sorted(companies[number]))
        if len(companies[number]) > 1:
            out.append(Finding("warning", "R004", number, f"exists in {len(companies[number])} companies ({where})"))
        first = next(c for c in orgs if c.number == number)
        match = dv_by_number.get(number)
        if not match:
            out.append(Finding("error", "R001", number, f"{first.name!r} ({where}) has no Dataverse account with this "
                               "account number"))
            continue
        if all(norm(a.name) != norm(first.name) for a in match):
            out.append(Finding("warning", "R003", number, f"name differs: Business Central {first.name!r}, "
                               f"Dataverse {match[0].name!r}"))
        if first.blocked in ("Ship", "Invoice", "All"):
            out.append(Finding("info", "R006", number, f"{first.name!r} is blocked in Business Central ({first.blocked})"))
    for number in sorted(dv_by_number):
        if number not in companies:
            out.append(Finding("warning", "R002", number, f"Dataverse account {dv_by_number[number][0].name!r} has no "
                               "Business Central customer"))
    if people:
        out.append(Finding("info", "R005", "Person", f"{len(people)} customer(s) of type Person skipped "
                           "(contacts, not accounts)"))
    return out


def summary(bc: List[BcCustomer], dv: List[DvAccount], company_type: str = "Company") -> List[str]:
    orgs = [c for c in bc if c.type == company_type]
    companies = sorted({c.company for c in bc})
    return [f"Business Central: {len(bc)} customer(s) in {len(companies)} company(ies) "
            f"({', '.join(companies) or '-'}); {len(orgs)} of type {company_type}",
            f"Dataverse: {len(dv)} account(s) with an account number"]
