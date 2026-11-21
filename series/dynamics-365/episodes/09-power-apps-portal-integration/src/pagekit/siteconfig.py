"""Read the parts of a downloaded Power Pages site that decide what the Web API can do.

`pac pages download` writes the site as YAML + HTML (Learn: "structured in YAML and HTML formats"). Learn's
deployment-profile example shows site settings as `adx_name` / `adx_value`. The other field names below
(`adx_entityname`, `adx_scope`, privilege flags, role links) are NOT quoted on Learn: they are collected in the
FIELDS dict so `pagekit inspect` on a real download can confirm them and one place fixes any difference.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

FIELDS = {
    "setting_name": "adx_name",
    "setting_value": "adx_value",
    "perm_table": "adx_entitylogicalname",
    "perm_scope": "adx_scope",
    "perm_name": "adx_entitypermissionname",
    "perm_roles": "adx_entitypermission_webrole",
    "role_id": "adx_webroleid",
    "role_name": "adx_name",
    "role_anonymous": "adx_anonymoususersrole",
    "role_authenticated": "adx_authenticatedusersrole",
}
PRIVILEGES = {"adx_read": "read", "adx_create": "create", "adx_write": "write", "adx_delete": "delete",
              "adx_append": "append", "adx_appendto": "appendto"}
# portal "access type" option values (unverified on Learn; text labels are accepted too)
SCOPES = {756150000: "global", 756150001: "contact", 756150002: "account", 756150003: "parent", 756150004: "self"}

WEBAPI_SETTING = re.compile(r"^Webapi/(?P<table>[^/]+)/(?P<key>enabled|fields|UseFieldsFromView)$")


@dataclass
class TableSetting:
    table: str
    enabled: Optional[str] = None
    fields: Optional[str] = None
    use_view: Optional[str] = None

    @property
    def is_enabled(self) -> bool:
        return (self.enabled or "").strip().lower() == "true"

    @property
    def field_list(self) -> List[str]:
        return [f.strip() for f in (self.fields or "").split(",") if f.strip()]

    @property
    def view_columns(self) -> bool:
        return (self.use_view or "").strip().lower() == "true"


@dataclass
class Role:
    id: str
    name: str
    anonymous: bool = False
    authenticated: bool = False


@dataclass
class Permission:
    name: str
    table: str
    scope: str
    privileges: Set[str] = field(default_factory=set)
    role_ids: List[str] = field(default_factory=list)


@dataclass
class Site:
    settings: Dict[str, TableSetting]
    permissions: List[Permission]
    roles: Dict[str, Role]
    other_settings: Dict[str, str]


def _load(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name}: not valid YAML ({str(e).splitlines()[0]})") from None
    return data if isinstance(data, dict) else {}


def _files(folder: Path, pattern: str) -> List[Path]:
    return sorted(folder.glob(pattern)) if folder.is_dir() else []


def _scope(value) -> str:
    if isinstance(value, int):
        return SCOPES.get(value, str(value))
    return str(value or "").strip().lower()


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() == "true"


def _ids(value) -> List[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [str(i).strip().lower() for i in items if str(i).strip()]


def load_site(root: Path) -> Site:
    settings: Dict[str, TableSetting] = {}
    other: Dict[str, str] = {}
    for f in _files(root / "site-settings", "*.yml"):
        d = _load(f)
        name, value = d.get(FIELDS["setting_name"]), d.get(FIELDS["setting_value"])
        if not name:
            continue
        m = WEBAPI_SETTING.match(str(name))
        if not m:
            other[str(name)] = "" if value is None else str(value)
            continue
        ts = settings.setdefault(m["table"], TableSetting(m["table"]))
        text = "" if value is None else str(value)
        if m["key"] == "enabled":
            ts.enabled = text
        elif m["key"] == "fields":
            ts.fields = text
        else:
            ts.use_view = text
    perms = []
    for f in _files(root / "table-permissions", "*.yml"):
        d = _load(f)
        if not d.get(FIELDS["perm_table"]):
            continue
        privs = {label for key, label in PRIVILEGES.items() if _truthy(d.get(key))}
        perms.append(Permission(str(d.get(FIELDS["perm_name"]) or f.stem), str(d[FIELDS["perm_table"]]),
                                _scope(d.get(FIELDS["perm_scope"])), privs, _ids(d.get(FIELDS["perm_roles"]))))
    roles: Dict[str, Role] = {}
    for f in _files(root / "web-roles", "*.yml"):
        d = _load(f)
        rid = str(d.get(FIELDS["role_id"]) or "").lower()
        if rid:
            roles[rid] = Role(rid, str(d.get(FIELDS["role_name"]) or rid), _truthy(d.get(FIELDS["role_anonymous"])),
                              _truthy(d.get(FIELDS["role_authenticated"])))
    return Site(settings, perms, roles, other)
