"""Read an unpacked solution folder: Other/Solution.xml, Other/Customizations.xml, Workflows/*.json,
environmentvariabledefinitions/*/environmentvariabledefinition.xml."""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT_FLOW = "29"       # RootComponent type for a cloud flow (workflow)
ROOT_ENV_VAR = "380"   # RootComponent type for an environment variable definition


class SolutionError(Exception):
    """The folder isn't a readable unpacked solution."""


@dataclass
class Flow:
    flow_id: str
    name: str
    file: Path
    body: dict

    @property
    def definition(self) -> dict:
        return self.body["properties"]["definition"]

    @property
    def connection_references(self) -> dict:
        return self.body["properties"].get("connectionReferences", {})

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.body, sort_keys=True).encode()).hexdigest()[:12]


@dataclass
class EnvVar:
    schema: str
    display: str
    default: str
    type_id: str
    secret_store: str
    extra_files: list[str] = field(default_factory=list)  # anything besides the definition XML (current values)


@dataclass
class Solution:
    path: Path
    unique_name: str
    version_text: str
    managed: str
    publisher: str
    prefix: str
    root_flows: set[str]
    root_env_vars: set[str]
    flows: dict[str, Flow]
    env_vars: dict[str, EnvVar]
    conn_refs: dict[str, str]  # logical name -> connector id

    @property
    def version(self) -> tuple[int, ...]:
        return parse_version(self.version_text)


def parse_version(text: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(\.\d+){3}", text or ""):
        raise SolutionError(f"version {text!r} isn't major.minor.build.revision")
    return tuple(int(p) for p in text.split("."))


def _xml(path: Path) -> ET.Element:
    if not path.exists():
        raise SolutionError(f"missing {path}")
    return ET.fromstring(path.read_text(encoding="utf-8-sig"))


def load_solution(folder: str | Path) -> Solution:
    folder = Path(folder)
    root = _xml(folder / "Other" / "Solution.xml")
    manifest = root.find("SolutionManifest")
    if manifest is None:
        raise SolutionError("Solution.xml has no SolutionManifest")

    def text(parent, tag):
        node = parent.find(tag)
        return (node.text or "").strip() if node is not None else ""

    publisher = manifest.find("Publisher")
    roots = manifest.find("RootComponents")
    root_flows = {r.get("id", "").strip("{}").lower() for r in (roots if roots is not None else []) if r.get("type") == ROOT_FLOW}
    root_env = {r.get("schemaName", "") for r in (roots if roots is not None else []) if r.get("type") == ROOT_ENV_VAR}

    flows: dict[str, Flow] = {}
    for data in sorted((folder / "Workflows").glob("*.json.data.xml")) if (folder / "Workflows").exists() else []:
        wf = ET.fromstring(data.read_text(encoding="utf-8-sig"))
        fid = (wf.get("WorkflowId") or "").strip("{}").lower()
        json_name = data.name[: -len(".data.xml")]
        body = json.loads((data.parent / json_name).read_text(encoding="utf-8-sig"))
        flows[fid] = Flow(fid, wf.get("Name") or json_name, data.parent / json_name, body)

    env_vars: dict[str, EnvVar] = {}
    env_root = folder / "environmentvariabledefinitions"
    for d in sorted(env_root.iterdir()) if env_root.exists() else []:
        x = d / "environmentvariabledefinition.xml"
        if not x.exists():
            continue
        e = ET.fromstring(x.read_text(encoding="utf-8-sig"))
        dn = e.find("displayname")
        env_vars[e.get("schemaname")] = EnvVar(
            schema=e.get("schemaname"),
            display=(dn.get("default") if dn is not None else "") or "",
            default=text(e, "defaultvalue"),
            type_id=text(e, "type"),
            secret_store=text(e, "secretstore"),
            extra_files=sorted(p.name for p in d.iterdir() if p.name != "environmentvariabledefinition.xml"),
        )

    conn_refs: dict[str, str] = {}
    cust = _xml(folder / "Other" / "Customizations.xml")
    for c in cust.iter("connectionreference"):
        conn_refs[c.get("connectionreferencelogicalname")] = (c.findtext("connectorid") or "").strip()

    return Solution(
        path=folder,
        unique_name=text(manifest, "UniqueName"),
        version_text=text(manifest, "Version"),
        managed=text(manifest, "Managed"),
        publisher=text(publisher, "UniqueName") if publisher is not None else "",
        prefix=text(publisher, "CustomizationPrefix") if publisher is not None else "",
        root_flows=root_flows,
        root_env_vars=root_env,
        flows=flows,
        env_vars=env_vars,
        conn_refs=conn_refs,
    )
