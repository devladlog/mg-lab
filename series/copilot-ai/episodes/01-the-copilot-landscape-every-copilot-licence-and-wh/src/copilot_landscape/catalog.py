"""Load, validate and print the Copilot catalog (data/copilot-catalog.yaml)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from urllib.parse import urlparse

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "copilot-catalog.yaml"

LICENCE_MODELS = {"included", "add-on", "usage-based", "capacity", "per-user", "bundle", "free-tier"}
LAB_STATUSES = {"real-in-lab", "trial-in-lab", "check-in-lab", "needs-purchase", "needs-owner-account"}
OFFICIAL_HOSTS = {
    "learn.microsoft.com",
    "www.microsoft.com",
    "azure.microsoft.com",
    "docs.github.com",
    "github.com",
    "support.microsoft.com",
}
REQUIRED = ("id", "name", "vendor", "area", "licence_model", "summary", "lab_status", "episode", "sources")


def load_catalog(path: Path | str | None = None) -> dict:
    with open(path or DEFAULT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate(catalog: dict) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    problems: list[str] = []
    try:
        _dt.date.fromisoformat(str(catalog.get("verified_on")))
    except ValueError:
        problems.append("verified_on must be an ISO date")
    seen: set[str] = set()
    for entry in catalog.get("entries", []):
        eid = entry.get("id", "<no id>")
        for key in REQUIRED:
            if not entry.get(key):
                problems.append(f"{eid}: missing {key}")
        if eid in seen:
            problems.append(f"{eid}: duplicate id")
        seen.add(eid)
        if entry.get("licence_model") not in LICENCE_MODELS:
            problems.append(f"{eid}: unknown licence_model {entry.get('licence_model')!r}")
        if entry.get("lab_status") not in LAB_STATUSES:
            problems.append(f"{eid}: unknown lab_status {entry.get('lab_status')!r}")
        ep = entry.get("episode")
        if not isinstance(ep, int) or not 1 <= ep <= 24:
            problems.append(f"{eid}: episode must be 1..24")
        sources = entry.get("sources") or []
        for url in sources:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc not in OFFICIAL_HOSTS:
                problems.append(f"{eid}: source is not an official https URL: {url}")
        if entry.get("price") and entry.get("price_source") not in sources:
            problems.append(f"{eid}: price needs a price_source that is listed in sources")
        if not entry.get("price") and entry.get("price_source"):
            problems.append(f"{eid}: price_source without a price")
    return problems


def entries(catalog: dict, area: str | None = None, free_only: bool = False) -> list[dict]:
    """Filter entries. `free_only` keeps what needs no purchase: included or already real in the lab."""
    result = catalog["entries"]
    if area:
        result = [e for e in result if e["area"] == area]
    if free_only:
        result = [e for e in result if e["licence_model"] in {"included", "free-tier"}]
    return result


def to_markdown(items: list[dict]) -> str:
    lines = ["| Copilot | Licence model | Price (verified) | In the lab | Ep |", "|---|---|---|---|---|"]
    for e in items:
        price = e.get("price") or "not verified, see sources"
        lines.append(f"| {e['name']} | {e['licence_model']} | {price} | {e['lab_status']} | {e['episode']} |")
    return "\n".join(lines)


def to_text(items: list[dict]) -> str:
    width = max(len(e["name"]) for e in items) if items else 10
    out = []
    for e in items:
        out.append(f"{e['name']:<{width}}  [{e['licence_model']}]  lab: {e['lab_status']}")
        out.append(f"{'':<{width}}  {e.get('price') or 'price: see sources'}")
    return "\n".join(out)
