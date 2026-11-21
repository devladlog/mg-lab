"""Compare customers in finance and operations with accounts in Dataverse, by account number.

This is what dual-write keeps true automatically once the Customers V3 (accounts) map runs. Use it before the first
initial sync (what would collide, what is missing) and afterwards as a drift check.

R001 error    F&O organization customer with no Dataverse account carrying that accountnumber
R002 warning  Dataverse account with an accountnumber that is not an F&O customer
R003 warning  same number on both sides but the names differ (case and spacing ignored)
R004 warning  the same CustomerAccount exists in more than one company (dataAreaId): the Dataverse key is accountnumber
R005 info     F&O customers that are people (PartyType Person) are left out: they belong to the contacts map
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .customers import DvAccount, FoCustomer
from .findings import Finding


def norm(s: str) -> str:
    return " ".join(s.casefold().split())


def reconcile(fo: List[FoCustomer], dv: List[DvAccount], organization: str = "Organization") -> List[Finding]:
    out: List[Finding] = []
    orgs = [c for c in fo if c.party_type == organization]
    people = [c for c in fo if c.party_type != organization]
    dv_by_number: Dict[str, List[DvAccount]] = defaultdict(list)
    for a in dv:
        dv_by_number[a.number].append(a)
    companies: Dict[str, List[str]] = defaultdict(list)
    for c in orgs:
        companies[c.account].append(c.company)

    for number in sorted(companies):
        where = ", ".join(sorted(companies[number]))
        if len(companies[number]) > 1:
            out.append(Finding("warning", "R004", number, f"exists in {len(companies[number])} companies ({where})"))
        first = next(c for c in orgs if c.account == number)
        match = dv_by_number.get(number)
        if not match:
            out.append(Finding("error", "R001", number, f"{first.name!r} ({where}) has no Dataverse account with this "
                               "account number"))
        elif all(norm(a.name) != norm(first.name) for a in match):
            out.append(Finding("warning", "R003", number, f"name differs: F&O {first.name!r}, Dataverse {match[0].name!r}"))
    for number in sorted(dv_by_number):
        if number not in companies:
            out.append(Finding("warning", "R002", number, f"Dataverse account {dv_by_number[number][0].name!r} has no "
                               "finance and operations customer"))
    if people:
        out.append(Finding("info", "R005", "Person", f"{len(people)} customer(s) with PartyType Person skipped "
                           "(contacts map, not accounts)"))
    return out


def summary(fo: List[FoCustomer], dv: List[DvAccount], organization: str = "Organization") -> List[str]:
    orgs = [c for c in fo if c.party_type == organization]
    companies = sorted({c.company for c in fo})
    return [f"finance and operations: {len(fo)} customer(s) in {len(companies)} company(ies) "
            f"({', '.join(companies) or '-'}); {len(orgs)} organization(s)",
            f"Dataverse: {len(dv)} account(s) with an account number"]
