"""Build the installable app package: substitute ${{NAME}} placeholders, validate, zip with manifest.json at the root."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import yaml

from .findings import Finding, errors
from .icons import color_icon, outline_icon
from .validate import PLACEHOLDER, validate_package

TEXT_SUFFIXES = {".json", ".yaml", ".yml"}
GUID = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class PackageError(Exception):
    def __init__(self, findings: list[Finding]):
        super().__init__("\n".join(str(f) for f in findings))
        self.findings = findings


def substitute(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def build(folder: Path, out_zip: Path, values: dict[str, str], api_url: str | None = None, version: str | None = None) -> list[Finding]:
    """Returns warnings. Raises PackageError when the substituted package has errors."""
    folder, out_zip = Path(folder), Path(out_zip)
    if "APP_ID" in values and not GUID.match(values["APP_ID"]):
        raise PackageError([Finding("error", "APP_ID", "must be a GUID")])
    files: dict[str, bytes] = {}
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(folder).as_posix()
        data = p.read_bytes()
        if p.suffix in TEXT_SUFFIXES:
            text = substitute(data.decode("utf-8"), values)
            if rel == "openapi.yaml" and api_url:
                spec = yaml.safe_load(text)
                spec["servers"] = [{"url": api_url.rstrip("/")}]
                text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=120)
            if rel == "manifest.json" and version:
                doc = json.loads(text)
                doc["version"] = version
                text = json.dumps(doc, indent=2) + "\n"
            data = text.encode("utf-8")
        files[rel] = data
    files.setdefault("color.png", color_icon())
    files.setdefault("outline.png", outline_icon())

    # validate exactly what goes into the zip: write to a scratch folder next to the zip's parent
    scratch = out_zip.parent / (out_zip.stem + ".build")
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        for rel, data in files.items():
            target = scratch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        findings = validate_package(scratch, strict=True)
        if errors(findings):
            raise PackageError(errors(findings))
        if api_url and not api_url.startswith("https://"):
            raise PackageError([Finding("error", "api-url", "must start with https:// (Copilot calls the API from the cloud)")])
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in sorted(files, key=lambda r: (r != "manifest.json", r)):
                info = zipfile.ZipInfo(rel, date_time=(2026, 11, 21, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, files[rel])
        return findings
    finally:
        for p in sorted(scratch.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        scratch.rmdir()
