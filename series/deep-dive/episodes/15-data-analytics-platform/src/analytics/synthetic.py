"""Deterministic, fictional purchase requests for Contoso.

The generator builds the *complete history* of every request (when it was submitted, when and how it was decided).
`snapshot(history, asof)` returns what the operational table (`dbo.PurchaseRequests`) holds at a given moment, and
`delta(history, t1, t2)` returns the rows an incremental copy sees between two watermarks. That is exactly what
the Data Factory pipeline does, so the same functions seed the source database and fake nothing else.

There is no real data here: names, vendors and amounts are random draws with a fixed seed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import CATEGORIES, DEPARTMENTS, SLA_DAYS

T1 = pd.Timestamp("2026-10-31 18:00:00")   # first load of the lake
T2 = pd.Timestamp("2026-11-14 18:00:00")   # second (incremental) load
T3 = pd.Timestamp("2026-11-15 09:00:00")   # the four bad rows arrive
START = pd.Timestamp("2026-07-01")

_DEPT_SPEED = {"FIN": -0.6, "HR": 0.0, "IT": 0.3, "MKT": 0.1, "OPS": 0.4}      # bias on days to decide
_CAT_AMOUNT = {"Hardware": 7.4, "Software": 6.8, "Services": 7.8, "Travel": 5.6, "Facilities": 7.1}  # log-mean EUR
_VENDORS = ("Fabrikam", "Northwind", "Adventure Works", "Tailspin", "Wingtip", "Litware", "Proseware")


def generate_history(n: int = 1200, seed: int = 20261121, end: pd.Timestamp = T2) -> pd.DataFrame:
    """One row per request with final decision data, ids 1..n, submitted between START and `end`."""
    rng = np.random.default_rng(seed)
    span_s = (end - START).total_seconds()
    submitted = START + pd.to_timedelta(np.sort(rng.uniform(0, span_s, n)), unit="s")
    submitted = submitted.floor("min")
    dept = rng.choice(list(DEPARTMENTS), n, p=[0.2, 0.15, 0.3, 0.15, 0.2])
    cat = rng.choice(CATEGORIES, n, p=[0.3, 0.25, 0.25, 0.1, 0.1])
    amount = np.round(np.exp(rng.normal([_CAT_AMOUNT[c] for c in cat], 0.9)), 2)
    amount = np.clip(amount, 20, 250_000)
    vendor = rng.choice(_VENDORS, n)
    # days to decide: bigger amounts, month end and Fridays are slower; Finance is faster (this is the "signal")
    dow = submitted.dayofweek.to_numpy()
    month_end = (submitted.day.to_numpy() >= 25).astype(float)
    z = (-1.4 + 0.55 * (np.log1p(amount) - 7.0) + 0.9 * (dow >= 4) + 0.8 * month_end
         + np.array([_DEPT_SPEED[d] for d in dept]) + rng.normal(0, 0.8, n))
    days = np.clip(np.round(np.exp(z + 1.4) * 0.9), 0, 30)
    decided_on = submitted + pd.to_timedelta(days * 24 * 3600 + rng.integers(600, 36000, n), unit="s")
    approved = rng.random(n) > 0.12
    return pd.DataFrame({
        "RequestId": np.arange(1, n + 1),
        "DepartmentCode": dept,
        "Category": cat,
        "VendorName": vendor,
        "Amount": amount,
        "Currency": "EUR",
        "SubmittedOn": submitted,
        "DecidedOn": decided_on.floor("min"),
        "FinalStatus": np.where(approved, "Approved", "Rejected"),
    })


def snapshot(history: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """The operational table as it looked at `asof`: undecided requests are 'Submitted' with no ApprovedOn."""
    h = history[history["SubmittedOn"] <= asof].copy()
    decided = h["DecidedOn"] <= asof
    out = pd.DataFrame({
        "RequestId": h["RequestId"],
        "DepartmentCode": h["DepartmentCode"],
        "Category": h["Category"],
        "VendorName": h["VendorName"],
        "Amount": h["Amount"],
        "Currency": h["Currency"],
        "Status": np.where(decided, h["FinalStatus"], "Submitted"),
        "SubmittedOn": h["SubmittedOn"],
        "ApprovedOn": h["DecidedOn"].where(decided & (h["FinalStatus"] == "Approved")),
        "ModifiedOn": np.where(decided, h["DecidedOn"], h["SubmittedOn"]),
    })
    out["ModifiedOn"] = pd.to_datetime(out["ModifiedOn"])
    return out.reset_index(drop=True)


def delta(history: pd.DataFrame, t1: pd.Timestamp | None, t2: pd.Timestamp) -> pd.DataFrame:
    """Rows an incremental copy sees: ModifiedOn > t1 and <= t2 (t1 None means the very first run)."""
    s = snapshot(history, t2)
    mask = s["ModifiedOn"] <= t2
    if t1 is not None:
        mask &= s["ModifiedOn"] > t1
    return s[mask].reset_index(drop=True)


def defect_rows(df: pd.DataFrame, modified_on: pd.Timestamp | None = None) -> pd.DataFrame:
    """Four bad rows (ids 9001..9004), one per rule in silver. They are copies of the first row of `df`."""
    base = df.iloc[0]
    bad = []
    r = base.copy(); r["RequestId"] = 9001; r["Amount"] = -50.0; bad.append(r)                         # negative amount
    r = base.copy(); r["RequestId"] = 9002; r["DepartmentCode"] = "ZZZ"; bad.append(r)                 # unknown department
    r = base.copy(); r["RequestId"] = 9003; r["Status"] = "Approved"
    r["ApprovedOn"] = r["SubmittedOn"] - pd.Timedelta(days=1); bad.append(r)                            # approved before submitted
    r = base.copy(); r["RequestId"] = 9004; r["Status"] = "Archived"; bad.append(r)                    # status outside the list
    out = pd.DataFrame(bad).reset_index(drop=True)
    if modified_on is not None:
        out["ModifiedOn"] = modified_on
    return out


def inject_defects(df: pd.DataFrame) -> pd.DataFrame:
    """`df` plus the four bad rows (for tests and the offline dry run)."""
    return pd.concat([df, defect_rows(df)], ignore_index=True)


def write_bronze(df: pd.DataFrame, root, ingest_date: str, run_id: str) -> str:
    """Write one parquet file the way the pipeline's Copy activity does: bronze/purchase_requests/ingest_date=D/<file>."""
    import pathlib
    import duckdb
    folder = pathlib.Path(root) / "bronze" / "purchase_requests" / f"ingest_date={ingest_date}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"requests-{run_id}.parquet"
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY (SELECT * FROM df) TO '{path.as_posix()}' (FORMAT PARQUET)")
    con.close()
    return str(path)


def _lit(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
        return "NULL"
    if isinstance(v, pd.Timestamp):
        return "'" + v.strftime("%Y-%m-%dT%H:%M:%S") + "'"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.2f}"
    return "N'" + str(v).replace("'", "''") + "'"


COLUMNS = ["RequestId", "DepartmentCode", "Category", "VendorName", "Amount", "Currency", "Status",
           "SubmittedOn", "ApprovedOn", "ModifiedOn"]


def to_merge_sql(df: pd.DataFrame, batch: int = 200) -> str:
    """T-SQL that loads rows into dbo.PurchaseRequests with MERGE, so phase 2 updates existing rows. Run it in the source database."""
    cols = ", ".join(COLUMNS)
    parts = ["SET NOCOUNT ON;", ""]
    for i in range(0, len(df), batch):
        chunk = df.iloc[i:i + batch]
        values = ",\n".join("(" + ", ".join(_lit(row[c]) for c in COLUMNS) + ")" for _, row in chunk.iterrows())
        sets = ", ".join(f"t.{c} = s.{c}" for c in COLUMNS if c != "RequestId")
        vals = ", ".join(f"s.{c}" for c in COLUMNS)
        parts.append(
            f"MERGE dbo.PurchaseRequests AS t\nUSING (VALUES\n{values}\n) AS s ({cols})\n"
            f"ON t.RequestId = s.RequestId\n"
            f"WHEN MATCHED THEN UPDATE SET {sets}\n"
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals});\nGO\n"
        )
    return "\n".join(parts)
