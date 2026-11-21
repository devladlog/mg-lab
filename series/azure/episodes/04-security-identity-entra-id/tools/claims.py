"""
Show the claims that matter for authorization in an Entra access token, without printing the token.
For display only: this does NOT validate the signature (the API does that).

  az account get-access-token --scope api://<tenant>/contoso-orders/Orders.Read --query accessToken -o tsv \
    | python3 tools/claims.py
  python3 tools/claims.py --imds <resource> <client-id>     # inside Azure, with a managed identity (IMDS)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request

SHOWN = ["aud", "iss", "ver", "idtyp", "azp", "appid", "scp", "roles", "oid", "tid", "exp"]
IMDS = os.environ.get("IMDS_ENDPOINT", "http://169.254.169.254")


def payload(token: str) -> dict:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT (expected header.payload.signature)")
    p = parts[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def summary(claims: dict) -> dict:
    out = {k: claims[k] for k in SHOWN if k in claims}
    out["kind"] = "app-only" if claims.get("idtyp") == "app" or ("scp" not in claims and "roles" in claims) \
        else "delegated (user)" if "scp" in claims else "unknown"
    return out


def imds_token(resource: str, client_id: str) -> str:
    """Managed identity token from the Azure Instance Metadata Service (the endpoint Learn shows for ACI and VMs)."""
    query = urllib.parse.urlencode({"api-version": "2018-02-01", "resource": resource, "client_id": client_id})
    req = urllib.request.Request(f"{IMDS}/metadata/identity/oauth2/token?{query}", headers={"Metadata": "true"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)["access_token"]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--imds"]:
        if len(argv) != 3:
            print(__doc__, file=sys.stderr)
            return 2
        token = imds_token(argv[1], argv[2])
    else:
        token = sys.stdin.read()
    try:
        print(json.dumps(summary(payload(token)), indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"cannot read token: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
