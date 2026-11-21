#!/usr/bin/env python3
"""Save the running API's OpenAPI document as the committed snapshot.

    python3 tools/export_openapi.py http://localhost:8080 openapi.v1.json

The document the API generates is the contract. Committing it means a pull request that changes the
contract shows the change in its diff, and openapi_coverage.py can fail when the collection falls behind.
`servers` is dropped: it holds whatever host the API was reached on. Standard library only.
"""
from __future__ import annotations

import json
import sys
import urllib.request


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    base, out = argv[1].rstrip("/"), argv[2]
    with urllib.request.urlopen(f"{base}/openapi/v1.json", timeout=10) as r:
        doc = json.load(r)
    doc.pop("servers", None)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {out}: OpenAPI {doc['openapi']}, {len(doc['paths'])} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
