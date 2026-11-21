"""python -m custkit render | deploy | probe-rule | remove

render      offline: write the view's fetchxml/layoutxml and the patched sample form to ../out/ (no tenant)
deploy      column + web resource + form handler + view, in the solution, then publish (idempotent)
probe-rule  try to create a request with a big budget and no justification through the API: does the server refuse?
remove      tear-down: unregister the handler, delete the view and the web resource (keeps the column)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import components, deploy, formxml
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]
CONFIG = EPISODE / "customization.json"


def load_config(path: Path = CONFIG) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_script(cfg: Dict[str, Any]) -> bytes:
    path = EPISODE / cfg["webresource"]["file"]
    if not path.exists():
        raise SystemExit(f"{path} not found: run `npm ci && npm test` in formscript/ first (it builds the file)")
    return path.read_bytes()


def make_api(args, cfg) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env), solution=args.solution or cfg["solution"])


def render(cfg: Dict[str, Any], out_dir: Path, sample_form: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    otc = 10001  # placeholder for the offline render only; deploy reads the real ObjectTypeCode
    for name, text in (("view.fetchxml.xml", components.view_fetchxml(cfg)),
                       ("view.layoutxml.xml", components.view_layoutxml(cfg, otc))):
        p = out_dir / name
        p.write_text(text + "\n", encoding="utf-8")
        written.append(p)
    res = formxml.register_onload(sample_form.read_text(encoding="utf-8"),
                                  cfg["webresource"]["name"], cfg["form"]["onload"])
    p = out_dir / "main-form.patched.xml"
    p.write_text(res.xml + "\n", encoding="utf-8")
    written.append(p)
    for a in res.actions:
        print(f"form: {a}")
    for f in formxml.missing_fields(res.xml, cfg["form"]["required_fields"]):
        print(f"form: ! no control for {f}")
    return written


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="custkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-url", help="environment URL (default: $DATAVERSE_URL)")
    p.add_argument("--solution", help="unmanaged solution unique name (default: from customization.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--out", type=Path, default=EPISODE / "out")
    r.add_argument("--sample-form", type=Path, default=EPISODE / "tests" / "fixtures" / "main_form.xml")
    sub.add_parser("deploy")
    pr = sub.add_parser("probe-rule")
    pr.add_argument("--budget", type=int, default=120000)
    sub.add_parser("remove")
    args = p.parse_args(argv)

    cfg = load_config()
    try:
        if args.cmd == "render":
            for path in render(cfg, args.out, args.sample_form):
                print(f"wrote {path.relative_to(EPISODE) if path.is_relative_to(EPISODE) else path}")
            return 0
        api = make_api(args, cfg)
        if args.cmd == "deploy":
            rep = deploy.deploy(api, cfg, read_script(cfg))
            return 1 if rep.warnings else 0
        if args.cmd == "probe-rule":
            return 0 if deploy.probe_rule(api, cfg, args.budget) else 3
        if args.cmd == "remove":
            deploy.remove(api, cfg)
            return 0
    except DataverseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
