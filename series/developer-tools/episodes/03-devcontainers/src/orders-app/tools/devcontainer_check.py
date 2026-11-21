#!/usr/bin/env python3
"""Is the dev container image we pinned still being updated?

Dev container images carry two versions in their tags: the image's own version and the toolchain's.
`mcr.microsoft.com/devcontainers/dotnet:3-10.0-noble` = image major 3, .NET 10, Ubuntu noble.
Pinning the image major is good practice, but when the image moves to the next major the old tag
simply stops being rebuilt. Nothing fails: you just stay on old bits (we found a `1-` tag still on a
release candidate SDK a year after GA).

This script reads the image from devcontainer.json, compares the pinned tag with the floating tag
(the same tag without the image-version prefix) straight from the registry, and prints what the
image itself adds (Features, extensions) from its `devcontainer.metadata` label.

    python3 tools/devcontainer_check.py [path/to/devcontainer.json] [--image REF] [--json]

Exit codes: 0 up to date, 1 the pinned tag is behind the floating tag, 2 error.
No Docker needed: it talks to the registry's HTTP API (anonymous pull, OCI distribution spec).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

INDEX_TYPES = ",".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
PIN_PREFIX = re.compile(r"^(?P<pin>\d+(?:\.\d+){0,2})-(?P<rest>\d.*)$")  # 3-10.0-noble, not 3.12-bookworm

# fetch(url, accept) -> (status, headers, body). Injected in tests; real HTTP otherwise.
Fetch = Callable[[str, str], tuple[int, dict, bytes]]


def strip_jsonc(text: str) -> str:
    """devcontainer.json is JSON with Comments: drop // and /* */ comments and trailing commas, outside strings."""
    out: list[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            in_str = c != '"'
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1          # trailing comma: drop it
                continue
            out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_jsonc(path: Path) -> dict:
    return json.loads(strip_jsonc(path.read_text(encoding="utf-8-sig")))


@dataclass
class ImageRef:
    registry: str
    repository: str
    tag: str

    @classmethod
    def parse(cls, ref: str) -> "ImageRef":
        if "@" in ref:
            raise ValueError(f"{ref}: pinned by digest, nothing to compare")
        name, _, tag = ref.rpartition(":")
        if not name or "/" in tag:
            name, tag = ref, "latest"
        registry, _, repository = name.partition("/")
        if "." not in registry and ":" not in registry:      # docker.io short names
            registry, repository = "registry-1.docker.io", name if "/" in name else f"library/{name}"
        return cls(registry, repository, tag)

    def floating_tag(self) -> str | None:
        m = PIN_PREFIX.match(self.tag)
        return m.group("rest") if m else None

    def pinned_major(self) -> int | None:
        m = PIN_PREFIX.match(self.tag)
        return int(m.group("pin").split(".")[0]) if m else None

    def __str__(self) -> str:
        return f"{self.registry}/{self.repository}:{self.tag}"


@dataclass
class ImageInfo:
    tag: str
    version: str | None          # image version label, e.g. 3.0.1
    created: str | None
    toolchain: dict = field(default_factory=dict)       # *_VERSION env vars, e.g. DOTNET_SDK_VERSION
    features: list[str] = field(default_factory=list)   # Features baked into the image
    extensions: list[str] = field(default_factory=list)  # extensions the image asks VS Code to install

    @property
    def major(self) -> int | None:
        return int(self.version.split(".")[0]) if self.version and self.version[0].isdigit() else None


def http_fetch(url: str, accept: str, token: str | None = None) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "devcontainer-check"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class Registry:
    """Minimal anonymous client for the OCI distribution API (with the Bearer token challenge)."""

    def __init__(self, fetch: Fetch | None = None):
        self._fetch = fetch
        self._token: str | None = None

    def get(self, url: str, accept: str) -> bytes:
        if self._fetch:                     # tests
            status, _, body = self._fetch(url, accept)
        else:
            status, headers, body = http_fetch(url, accept, self._token)
            if status == 401 and "www-authenticate" in {k.lower() for k in headers}:
                challenge = next(v for k, v in headers.items() if k.lower() == "www-authenticate")
                self._token = self._anonymous_token(challenge)
                status, _, body = http_fetch(url, accept, self._token)
        if status != 200:
            raise RuntimeError(f"GET {url} -> HTTP {status}")
        return body

    @staticmethod
    def _anonymous_token(challenge: str) -> str:
        params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        query = "&".join(f"{k}={params[k]}" for k in ("service", "scope") if k in params)
        status, _, body = http_fetch(f"{params['realm']}?{query}", "application/json")
        if status != 200:
            raise RuntimeError(f"anonymous token request failed: HTTP {status}")
        data = json.loads(body)
        return data.get("token") or data["access_token"]

    def image_info(self, ref: ImageRef, arch: str = "amd64") -> ImageInfo:
        base = f"https://{ref.registry}/v2/{ref.repository}"
        doc = json.loads(self.get(f"{base}/manifests/{ref.tag}", INDEX_TYPES))
        if "manifests" in doc:                                   # multi-arch index
            match = [m for m in doc["manifests"]
                     if m.get("platform", {}).get("os") == "linux" and m["platform"].get("architecture") == arch]
            if not match:
                raise RuntimeError(f"{ref}: no linux/{arch} image")
            doc = json.loads(self.get(f"{base}/manifests/{match[0]['digest']}", INDEX_TYPES))
        config = json.loads(self.get(f"{base}/blobs/{doc['config']['digest']}", "application/json"))
        cfg = config.get("config", {})
        labels = cfg.get("Labels") or {}
        env = dict(e.split("=", 1) for e in cfg.get("Env") or [] if "=" in e)
        meta = json.loads(labels.get("devcontainer.metadata", "[]"))
        return ImageInfo(
            tag=ref.tag,
            version=labels.get("version") or labels.get("org.opencontainers.image.version"),
            created=config.get("created"),
            toolchain={k: v for k, v in env.items() if k.endswith("_VERSION")},
            features=[m["id"] for m in meta if "id" in m],
            extensions=[x for m in meta for x in m.get("customizations", {}).get("vscode", {}).get("extensions", [])],
        )


def check(image: str, registry: Registry) -> tuple[int, dict]:
    ref = ImageRef.parse(image)
    pinned = registry.image_info(ref)
    report: dict = {"image": str(ref), "pinned": pinned.__dict__, "status": "ok", "message": ""}
    floating = ref.floating_tag()
    if floating is None:
        report["message"] = "tag has no image-version prefix (e.g. 3-10.0): you always get the newest image"
        return 0, report
    latest = registry.image_info(ImageRef(ref.registry, ref.repository, floating))
    report["floating"] = latest.__dict__
    if latest.major and (ref.pinned_major() or 0) < latest.major:
        report["status"] = "stale"
        report["message"] = (f"pinned image major {ref.pinned_major()} but '{floating}' is on {latest.version}: "
                             f"the pinned tag no longer gets updates. Review the changes, then move to "
                             f"{latest.major}-{floating}.")
        return 1, report
    if pinned.created and latest.created and pinned.created < latest.created:
        report["message"] = f"same major, but '{floating}' was rebuilt later: rebuild the container to pick it up"
    return 0, report


def print_report(report: dict) -> None:
    p = report["pinned"]
    print(f"Image:     {report['image']}")
    print(f"Pinned:    {p['tag']:<16} image {p['version']}  built {(p['created'] or '?')[:10]}  "
          + "  ".join(f"{k}={v}" for k, v in p["toolchain"].items() if "SDK" in k or k == "PYTHON_VERSION"))
    if "floating" in report:
        f = report["floating"]
        print(f"Floating:  {f['tag']:<16} image {f['version']}  built {(f['created'] or '?')[:10]}  "
              + "  ".join(f"{k}={v}" for k, v in f["toolchain"].items() if "SDK" in k or k == "PYTHON_VERSION"))
    print(f"In image:  features {', '.join(p['features']) or '-'}")
    print(f"           extensions {', '.join(p['extensions']) or '-'}")
    mark = {"ok": "OK", "stale": "STALE"}[report["status"]]
    text = f"{mark}{': ' + report['message'] if report['message'] else ''}"
    print(textwrap.fill(text, width=100, subsequent_indent="       "))


def main(argv: list[str] | None = None, registry: Registry | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("config", nargs="?", default=".devcontainer/devcontainer.json")
    ap.add_argument("--image", help="check this image reference instead of the one in the config")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    try:
        image = args.image or load_jsonc(Path(args.config)).get("image")
        if not image:
            print("devcontainer.json has no 'image' (Dockerfile or Compose based): nothing to check", file=sys.stderr)
            return 2
        code, report = check(image, registry or Registry())
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2)) if args.json else print_report(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
