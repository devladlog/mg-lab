#!/usr/bin/env python3
"""Fill the {{tokens}} in deploy/*.yaml from the Bicep deployment outputs and write the result to an output folder.

    az deployment group show -g rg-mglab-deep-dive-10 -n main --query properties.outputs -o json > outputs.json
    python3 scripts/render_manifests.py --outputs outputs.json --image <acr>.azurecr.io/finance-worker:1 --out build/

Fails (exit 1) when a manifest holds a token that has no value, or when a value is missing, so a half-filled manifest
never reaches the cluster. Only the Python standard library is used.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def load_outputs(path: Path) -> dict[str, str]:
    """`az deployment group show --query properties.outputs` gives {name: {type, value}}; accept a flat map too."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in raw.items()}


def render(text: str, values: dict[str, str], source: str = "<text>") -> str:
    missing = sorted({m.group(1) for m in TOKEN.finditer(text) if not str(values.get(m.group(1), "")).strip()})
    if missing:
        raise ValueError(f"{source}: no value for token(s) {', '.join(missing)}")
    return TOKEN.sub(lambda m: str(values[m.group(1)]), text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", required=True, type=Path, help="JSON from the Bicep deployment outputs")
    ap.add_argument("--image", required=True, help="full image reference, for example myacr.azurecr.io/finance-worker:1")
    ap.add_argument("--deploy-dir", type=Path, default=Path(__file__).resolve().parent.parent / "deploy")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)

    values = load_outputs(a.outputs)
    values["image"] = a.image
    a.out.mkdir(parents=True, exist_ok=True)
    files = sorted(a.deploy_dir.glob("*.yaml"))
    if not files:
        print(f"no manifests in {a.deploy_dir}", file=sys.stderr)
        return 1
    try:
        for f in files:
            (a.out / f.name).write_text(render(f.read_text(encoding="utf-8"), values, f.name), encoding="utf-8")
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"rendered {len(files)} manifests into {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
