"""An in-memory SharePoint site for local tests: lists with versions and a change log, a document
library with folders, files and permissions, users, and the connector operations our flow calls.

It is a test double, not SharePoint. It implements what Microsoft Learn documents for the operations
we use and is strict where Learn is explicit:

- "When an item or a file is modified" (GetOnChangedItems) fires on modifications, not on creation,
  and returns the Trigger Window Start/End tokens.
- "Get changes for an item or a file (properties only)" (GetItemChanges) needs versioning on the list
  and compares the item between two tokens.
- "Update item" (PatchItem) needs a value for every required column.
- A REST MERGE keeps every property you don't send; a list item MERGE needs the list's
  ListItemEntityTypeFullName as __metadata.type.

Where Learn says nothing (the exact error texts, what CreateNewFolder does with a folder that already
exists, the shape of ColumnHasChanged), the behaviour here is an assumption and is labelled as one.
"""
from __future__ import annotations

import copy
import itertools
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .rest import RestRouter


class SPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status, self.message = status, message


@dataclass
class Version:
    seq: int                 # change-log position when this version was written
    fields: dict
    editor: str


@dataclass
class Item:
    id: int
    versions: list[Version] = field(default_factory=list)
    modified_at: list[int] = field(default_factory=list)   # change-log positions of every edit (not the creation)

    @property
    def current(self) -> dict:
        return self.versions[-1].fields

    def at(self, seq: int) -> dict | None:
        """The item as it was at change-log position seq (None if it didn't exist yet)."""
        found = None
        for v in self.versions:
            if v.seq <= seq:
                found = v.fields
        return found


@dataclass
class Folder:
    path: str                                # library-relative, e.g. "PR-00041"
    item_id: int
    unique_permissions: bool = False
    role_assignments: list[tuple[int, int]] = field(default_factory=list)   # (principal id, role definition id)


@dataclass
class SPList:
    title: str
    url_name: str                            # last segment of the list URL, e.g. "PurchaseRequests"
    columns: dict[str, str]                  # internal name -> "text" | "number" | "choice" | "user"
    required: tuple[str, ...] = ("Title",)
    versioning: bool = True
    library: bool = False
    items: dict[int, Item] = field(default_factory=dict)
    folders: dict[str, Folder] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)   # library-relative path -> {item_id, content}
    last_poll: int = 0
    next_id: itertools.count = field(default_factory=lambda: itertools.count(1))

    @property
    def entity_type(self) -> str:
        return f"SP.Data.{self.url_name}{'Item' if self.library else 'ListItem'}"


class Site:
    def __init__(self, url: str = "https://contoso.sharepoint.com/sites/Purchasing",
                 now: datetime | None = None):
        self.url = url.rstrip("/")
        self.path = "/" + self.url.split("/", 3)[3]          # server-relative, e.g. /sites/Purchasing
        self.lists: dict[str, SPList] = {}
        self.seq = 0
        self.clock = now or datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
        self.directory: dict[str, dict] = {}                 # claims -> user (who exists in Entra)
        self.site_users: dict[str, dict] = {}                # claims -> user added to the site (EnsureUser)
        self.role_definitions = {"Full Control": 1, "Edit": 2, "Contribute": 3, "Read": 4}  # ids are fake
        self.site_role_assignments: list[tuple[int, int]] = []
        self._principal_ids = itertools.count(10)
        self.calls: list[tuple[str, str]] = []               # (operationId or REST verb, target) in call order
        self.rest = RestRouter(self)

    # ---------------------------------------------------------------- setup helpers
    def add_list(self, sp_list: SPList) -> SPList:
        self.lists[sp_list.title] = sp_list
        return sp_list

    def add_user(self, email: str, name: str) -> dict:
        claims = f"i:0#.f|membership|{email}"
        user = {"Claims": claims, "DisplayName": name, "Email": email}
        self.directory[claims] = user
        return user

    def add_site_group(self, name: str, role: str) -> int:
        """A site group (owners, members...) with a role on the whole site: inherited by every folder."""
        pid = next(self._principal_ids)
        self.site_users[f"group:{name}"] = {"Id": pid, "Title": name}
        self.site_role_assignments.append((pid, self.role_definitions[role]))
        return pid

    def tick(self, minutes: int = 1):
        self.clock += timedelta(minutes=minutes)

    def _log(self) -> int:
        self.seq += 1
        return self.seq

    # ---------------------------------------------------------------- what people do in the browser
    def create_item(self, list_title: str, fields: dict, author: dict) -> int:
        sp = self.lists[list_title]
        item_id = next(sp.next_id)
        data = {c: None for c in sp.columns}
        data.update(fields)
        data.update(ID=item_id, Author=author, Editor=author, Created=self._now(), Modified=self._now())
        sp.items[item_id] = Item(item_id, [Version(self._log(), data, author["Email"])])
        return item_id

    def edit_item(self, list_title: str, item_id: int, changes: dict, editor: dict) -> None:
        self._write(self.lists[list_title], item_id, changes, editor)

    def _write(self, sp: SPList, item_id: int, changes: dict, editor: dict) -> None:
        item = sp.items[item_id]
        data = copy.deepcopy(item.current)
        for k in changes:
            if k not in sp.columns and k != "Title":
                raise SPError(400, f"Column '{k}' does not exist in list '{sp.title}'")
        data.update(changes)
        data.update(Editor=editor, Modified=self._now())
        version = Version(self._log(), data, editor["Email"])
        item.modified_at.append(version.seq)
        if sp.versioning:
            item.versions.append(version)
        else:
            item.versions = [version]           # no history: only the latest state is kept

    def _now(self) -> str:
        return self.clock.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---------------------------------------------------------------- trigger
    def poll_modified(self, list_title: str) -> list[dict]:
        """GetOnChangedItems: items modified (not created) since the last poll, latest state, with tokens."""
        sp = self.lists[list_title]
        start, end = sp.last_poll, self.seq
        bodies = []
        for item in sp.items.values():
            if not any(start < seq <= end for seq in item.modified_at):
                continue
            body = self._item_body(sp, item.current)
            body["{TriggerWindowStartToken}"] = token(start)
            body["{TriggerWindowEndToken}"] = token(end)
            bodies.append(body)
        sp.last_poll = end
        return bodies

    def _item_body(self, sp: SPList, data: dict) -> dict:
        body = {"@odata.etag": f"\"{len(sp.items[data['ID']].versions)}\"", "ItemInternalId": str(data["ID"])}
        for k, v in data.items():
            if sp.columns.get(k) == "choice" and v is not None:
                body[k] = {"Value": v}
            else:
                body[k] = v
        body["{Link}"] = f"{self.url}/Lists/{sp.url_name}/DispForm.aspx?ID={data['ID']}"
        return body

    # ---------------------------------------------------------------- connector operations
    def connector(self, inputs: dict) -> dict:
        """Entry point for a mocked SharePoint connector action: dispatch on operationId."""
        op = inputs["host"]["operationId"]
        params = inputs.get("parameters", {})
        if params.get("dataset", "").rstrip("/") != self.url:
            return _fail(404, f"Site '{params.get('dataset')}' not found")
        try:
            handler = getattr(self, f"_op_{op}")
        except AttributeError:
            raise NotImplementedError(f"spfake doesn't implement {op}") from None
        self.calls.append((op, str(params.get("table") or params.get("parameters/uri") or params.get("folderPath"))))
        try:
            status, body = handler(params)
        except SPError as e:
            return _fail(e.status, e.message)
        return {"status": "Succeeded", "statusCode": status, "body": body}

    def _list(self, params) -> SPList:
        title = params.get("table")
        if title not in self.lists:
            raise SPError(404, f"List '{title}' does not exist at site with URL '{self.url}'")
        return self.lists[title]

    def _op_GetItemChanges(self, p):
        sp = self._list(p)
        if not sp.versioning:
            # Learn: "The list must have Versioning turned on." (error text is the fake's own)
            raise SPError(400, "Versioning must be enabled on the list to get changes")
        item = sp.items.get(int(p["id"]))
        if item is None:
            raise SPError(404, "Item not found")
        since, until = parse_token(p["since"]), parse_token(p.get("until")) if p.get("until") else self.seq
        before, after = item.at(since), item.at(until)
        if after is None:
            raise SPError(404, "Item did not exist at the end of the window")
        cols = [c for c in sp.columns] + ["Title"]
        changed = {c: (before is None) or before.get(c) != after.get(c) for c in dict.fromkeys(cols)}
        # Shape assumed from the designer's dynamic content ("Has Column Changed: <column>"); not documented on Learn.
        return 200, {"SinceVersionExisted": before is not None, "ColumnHasChanged": changed}

    def _op_PatchItem(self, p):
        sp = self._list(p)
        item_id = int(p["id"])
        if item_id not in sp.items:
            raise SPError(404, "Item not found")
        changes = _item_params(p, sp)
        missing = [c for c in sp.required if c not in changes]
        if missing:
            # Learn: "you always need to specify a value for all the mandatory fields" (text is the fake's own)
            raise SPError(400, f"Required column(s) missing: {', '.join(missing)}")
        self._write(sp, item_id, changes, self.connection_user)
        return 200, self._item_body(sp, sp.items[item_id].current)

    def _op_CreateNewFolder(self, p):
        sp = self._list(p)
        if not sp.library:
            raise SPError(400, "Folders are created in a library in this fake")
        path = p["path"].strip("/")
        if not path or re.search(r'["*:<>?/\\|]', path.split("/")[-1]):
            raise SPError(400, f"Invalid folder name '{path}'")
        if path not in sp.folders:   # assumption: an existing folder is returned, not an error (not on Learn)
            item_id = next(sp.next_id)
            sp.folders[path] = Folder(path, item_id)
            self._log()
        f = sp.folders[path]
        return 200, {"ID": f.item_id, "Name": path.split("/")[-1], "{FullPath}": f"{sp.url_name}/{path}", "{IsFolder}": True}

    def _op_CreateFile(self, p):
        folder = p["folderPath"].strip("/")
        lib_name, _, sub = folder.partition("/")
        sp = next((l for l in self.lists.values() if l.library and l.url_name == lib_name), None)
        if sp is None:
            raise SPError(404, f"Library '{lib_name}' not found: Folder Path must start with an existing library")
        if sub and sub not in sp.folders:
            raise SPError(404, f"Folder '{folder}' not found")
        path = f"{sub}/{p['name']}" if sub else p["name"]
        item_id = next(sp.next_id)
        sp.files[path] = {"item_id": item_id, "content": p["body"], "fields": {}}
        self._log()
        return 200, {"ItemId": item_id, "Id": f"%252f{lib_name}%252f{path}", "Name": p["name"],
                     "Path": f"/{lib_name}/{path}", "IsFolder": False}

    def _op_PatchFileItem(self, p):
        sp = self._list(p)
        item_id = int(p["id"])
        f = next((f for f in sp.files.values() if f["item_id"] == item_id), None)
        if f is None:
            raise SPError(404, "File item not found")
        f["fields"].update(_item_params(p, sp))
        self._log()
        return 200, {"ID": item_id, **f["fields"]}

    def _op_HttpRequest(self, p):
        return self.rest.handle(p.get("parameters/method", "GET"), p["parameters/uri"],
                                p.get("parameters/headers") or {}, p.get("parameters/body"))

    # The account the flow's SharePoint connection signs in with (edits show "Modified by" this user).
    connection_user = {"Claims": "i:0#.f|membership|labadmin@contoso.com", "DisplayName": "Lab Admin",
                       "Email": "labadmin@contoso.com"}

    # ---------------------------------------------------------------- helpers for tests
    def folder(self, library: str, path: str) -> Folder:
        return self.lists[library].folders[path]

    def effective_role_assignments(self, library: str, path: str) -> list[tuple[int, int]]:
        f = self.folder(library, path)
        return list(f.role_assignments) if f.unique_permissions else list(self.site_role_assignments)

    def user_id(self, email: str) -> int | None:
        u = self.site_users.get(f"i:0#.f|membership|{email}")
        return u["Id"] if u else None


def token(seq: int) -> str:
    """Opaque window token. Real tokens are opaque too; never parse them in a flow."""
    return f"0x{seq:016x}"


def parse_token(text: str) -> int:
    if not isinstance(text, str) or not re.fullmatch(r"0x[0-9a-f]{16}", text):
        raise SPError(400, f"'{text}' isn't a Trigger Window token (this fake doesn't accept version labels or dates)")
    return int(text, 16)


def _item_params(p: dict, sp: SPList) -> dict:
    out: dict[str, Any] = {}
    for key, value in p.items():
        if not key.startswith("item/"):
            continue
        parts = key.split("/")[1:]
        column = parts[0]
        if column not in sp.columns and column != "Title":
            raise SPError(400, f"Column '{column}' does not exist in '{sp.title}'")
        if sp.columns.get(column) == "choice" and parts[1:] != ["Value"]:
            raise SPError(400, f"Choice column '{column}' is set with item/{column}/Value")
        out[column] = value
    return out


def _fail(status: int, message: str) -> dict:
    return {"status": "Failed", "statusCode": status, "body": {"error": {"message": message}},
            "error": f"{status}: {message}"}
