"""Three Python gotchas from the episode. Pure Python: no Azure, no emulator, no sign-in.

Run from the episode folder:  python demo/gotchas.py
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from contoso_azure.domain import parse_requests

CSV = "code,title,department,budget,submitted\nPR-2026-0001,Laptops,IT,12000,2026-11-01\n"


def bom() -> None:
    raw = ("﻿" + CSV).encode("utf-8")  # what Excel's "CSV UTF-8" writes
    print("1. byte order mark")
    print("   decoded as utf-8     :", len(parse_requests(raw.decode("utf-8")).valid), "valid rows")
    print("   decoded as utf-8-sig :", len(parse_requests(raw.decode("utf-8-sig")).valid), "valid rows")


def decimal_json() -> None:
    print("2. Decimal and JSON")
    try:
        json.dumps({"budget": Decimal("49999.99")})
    except TypeError as problem:
        print("   json.dumps(Decimal)  :", problem)
    print("   as a string          :", json.dumps({"budget": str(Decimal("49999.99"))}))
    print("   float 0.1 + 0.2      :", 0.1 + 0.2, "| Decimal:", Decimal("0.1") + Decimal("0.2"))


async def task_group() -> None:
    async def upload(name: str) -> None:
        if name == "PR-2":
            raise ConnectionError(f"{name} failed")
        await asyncio.sleep(0.01)

    print("3. TaskGroup")
    try:
        async with asyncio.TaskGroup() as group:
            for name in ("PR-1", "PR-2", "PR-3"):
                group.create_task(upload(name))
    except ConnectionError:
        print("   except ConnectionError: caught")
    except ExceptionGroup as grouped:
        print("   except ConnectionError: NOT reached")
        print("   ExceptionGroup        :", [str(e) for e in grouped.exceptions])
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(upload("PR-2"))
    except* ConnectionError as grouped:
        print("   except* ConnectionError: caught", len(grouped.exceptions), "error")


if __name__ == "__main__":
    bom()
    decimal_json()
    asyncio.run(task_group())
