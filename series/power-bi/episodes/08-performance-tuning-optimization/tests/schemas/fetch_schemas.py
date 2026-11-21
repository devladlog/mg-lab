#!/usr/bin/env python3
"""Download (once, at authoring time) the published JSON schemas the tests validate against, plus every schema
they reference, into a local mirror of developer.microsoft.com/json-schemas/... so the tests run offline.

    python tests/schemas/fetch_schemas.py
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://developer.microsoft.com/json-schemas/"
ROOTS = [
    "fabric/pbip/pbipProperties/1.0.0/schema.json",
    "fabric/item/report/definitionProperties/2.0.0/schema.json",
    "fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "fabric/item/report/definition/report/3.1.0/schema.json",
    "fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "fabric/item/report/definition/page/2.1.0/schema.json",
    "fabric/item/report/definition/visualContainer/2.4.0/schema.json",
]
THEME = ("https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/"
         "Report%20Theme%20JSON%20Schema/reportThemeSchema-2.159.json")


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def refs(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                yield v.split("#")[0]
            else:
                yield from refs(v)
    elif isinstance(node, list):
        for x in node:
            yield from refs(x)


def main():
    todo, done = [BASE + r for r in ROOTS], set()
    while todo:
        url = todo.pop()
        if url in done:
            continue
        done.add(url)
        doc = fetch(url)
        rel = url[len(BASE):]
        out = HERE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        for r in set(refs(doc)):
            todo.append(urllib.parse.urljoin(url, r))
        print("saved", rel)
    theme = fetch(THEME)
    (HERE / "reportThemeSchema-2.159.json").write_text(json.dumps(theme, separators=(",", ":")), encoding="utf-8")
    print("saved reportThemeSchema-2.159.json")


if __name__ == "__main__":
    main()
