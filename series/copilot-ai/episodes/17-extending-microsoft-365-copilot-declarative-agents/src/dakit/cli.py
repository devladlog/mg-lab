from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import licence
from .contract import run_contract
from .findings import errors
from .openapi_lint import lint_openapi
from .package import PackageError, build
from .validate import validate_package


def _print(findings) -> int:
    for f in findings:
        print(f)
    n_err = len(errors(findings))
    print(f"{n_err} error(s), {len(findings) - n_err} warning(s)")
    return 1 if n_err else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dakit", description="Check, price and package a declarative agent with an API plugin.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate an app package folder against the official schemas and Learn's rules")
    v.add_argument("folder", type=Path)
    v.add_argument("--strict", action="store_true", help="unresolved ${{...}} placeholders are errors")

    o = sub.add_parser("lint-openapi", help="lint an OpenAPI description for use as an API plugin")
    o.add_argument("file", type=Path)

    c = sub.add_parser("licence", help="which licence model does this declarative agent manifest need?")
    c.add_argument("manifest", type=Path)
    c.add_argument("--max", choices=licence.TIERS, help="exit 1 when the agent needs more than this tier")

    k = sub.add_parser("contract", help="run the API code against the OpenAPI description (in process, no network)")
    k.add_argument("openapi", type=Path)
    k.add_argument("--today", default="2026-11-21")

    b = sub.add_parser("package", help="substitute placeholders, validate and zip the app package")
    b.add_argument("folder", type=Path)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--app-id", required=True, help="GUID for the app (new GUID per environment)")
    b.add_argument("--api-url", required=True, help="https URL of the deployed API (for example a dev tunnel)")
    b.add_argument("--auth-id", required=True, help="API key registration id (VENDOR_API_KEY_REGISTRATION_ID)")
    b.add_argument("--version", help="app version, for example 1.0.1")

    a = p.parse_args(argv)
    if a.cmd == "validate":
        return _print(validate_package(a.folder, strict=a.strict))
    if a.cmd == "lint-openapi":
        return _print(lint_openapi(a.file))
    if a.cmd == "licence":
        result = licence.assess_file(a.manifest)
        print(licence.render(result))
        if a.max and licence.TIERS.index(result["needs"]) > licence.TIERS.index(a.max):
            print(f"FAIL: needs {result['needs']}, allowed {a.max}")
            return 1
        return 0
    if a.cmd == "contract":
        from vendor_api.app import create_app
        day = date.fromisoformat(a.today)
        findings = run_contract(a.openapi, create_app("k", today=lambda: day))
        return _print(findings)
    if a.cmd == "package":
        try:
            warnings = build(a.folder, a.out, {"APP_ID": a.app_id, "VENDOR_API_KEY_REGISTRATION_ID": a.auth_id},
                             api_url=a.api_url, version=a.version)
        except PackageError as e:
            print(e, file=sys.stderr)
            return 1
        for w in warnings:
            print(w)
        print(f"wrote {a.out}")
        return 0
    return 2
