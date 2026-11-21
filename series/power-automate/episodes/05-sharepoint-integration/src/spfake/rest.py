"""The SharePoint REST endpoints our flow sends through "Send an HTTP request to SharePoint".

Only these routes exist; anything else answers 404, so a typo in a URI fails a test instead of passing.
Endpoint shapes follow Microsoft Learn ("Working with folders and files with REST", "Working with lists
and list items with REST", "Set custom permissions on a list by using the REST interface"); EnsureUser
follows the client object model method Web.EnsureUser(logonName), since REST URIs mirror that model.

Response format: with "Accept: application/json;odata=nometadata" the entity comes back as a plain
object ({"Id": 12}); without it, this fake answers in the verbose shape ({"d": {"Id": 12}}), which is
what breaks body('...')?['Id'] when the header is forgotten.
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

_FOLDER = r"_api/web/GetFolderByServerRelativeUrl\('(?P<path>[^']+)'\)/ListItemAllFields"
ROUTES = [
    ("POST", r"_api/web/ensureuser", "ensure_user"),
    ("GET", r"_api/web/roledefinitions/getbyname\('(?P<name>[^']+)'\)(\?\$select=Id)?", "role_definition"),
    ("POST", _FOLDER + r"/breakroleinheritance\(copyRoleAssignments=(?P<copy>true|false),"
                       r"clearSubscopes=(?P<clear>true|false)\)", "break_inheritance"),
    ("POST", _FOLDER + r"/roleassignments/addroleassignment\(principalid=(?P<pid>\d+),roledefid=(?P<rid>\d+)\)",
     "add_role_assignment"),
    ("GET", r"_api/web/lists/GetByTitle\('(?P<title>[^']+)'\)\?\$select=ListItemEntityTypeFullName", "entity_type"),
    ("POST", r"_api/web/lists/GetByTitle\('(?P<title>[^']+)'\)/items\((?P<id>\d+)\)", "merge_item"),
]


class RestRouter:
    def __init__(self, site):
        self.site = site

    def handle(self, method: str, uri: str, headers: dict, body):
        from .site import SPError
        h = {k.lower(): str(v) for k, v in headers.items()}
        method = method.upper()
        verb = h.get("x-http-method", method).upper()
        for m, pattern, name in ROUTES:
            match = re.fullmatch(pattern, uri.lstrip("/"), flags=re.IGNORECASE)
            if match and m == method:
                self.site.calls.append((f"REST {verb}", name))
                status, entity = getattr(self, name)(match.groupdict(), h, _json(body), verb)
                return status, self._shape(entity, h)
        raise SPError(404, f"No REST endpoint matches {method} {uri}")

    @staticmethod
    def _shape(entity, h):
        if entity is None:
            return None
        if "odata=nometadata" in h.get("accept", "").replace(" ", ""):
            return entity
        return {"d": entity}

    # ------------------------------------------------------------------ routes
    def ensure_user(self, g, h, body, verb):
        from .site import SPError
        logon = (body or {}).get("logonName")
        user = self.site.directory.get(logon)
        if user is None:
            raise SPError(404, f"The specified user {logon} could not be found.")
        if logon not in self.site.site_users:
            self.site.site_users[logon] = {"Id": next(self.site._principal_ids), "Title": user["DisplayName"],
                                           "Email": user["Email"], "LoginName": logon}
        return 200, dict(self.site.site_users[logon])

    def role_definition(self, g, h, body, verb):
        from .site import SPError
        name = g["name"]
        if name not in self.site.role_definitions:
            raise SPError(404, f"Permission level '{name}' does not exist")
        return 200, {"Id": self.site.role_definitions[name], "Name": name}

    def _folder(self, path):
        from .site import SPError
        path = unquote(path)
        prefix = self.site.path + "/"
        if not path.startswith(prefix):
            raise SPError(404, f"File Not Found: '{path}' isn't under {self.site.path}")
        lib_url, _, sub = path[len(prefix):].partition("/")
        sp = next((l for l in self.site.lists.values() if l.library and l.url_name == lib_url), None)
        if sp is None or sub not in sp.folders:
            raise SPError(404, f"File Not Found: {path}")
        return sp.folders[sub]

    def break_inheritance(self, g, h, body, verb):
        f = self._folder(g["path"])
        if not f.unique_permissions:
            f.unique_permissions = True
            f.role_assignments = list(self.site.site_role_assignments) if g["copy"].lower() == "true" else []
        self.site._log()
        return 200, None

    def add_role_assignment(self, g, h, body, verb):
        from .site import SPError
        f = self._folder(g["path"])
        pid, rid = int(g["pid"]), int(g["rid"])
        if rid not in self.site.role_definitions.values():
            raise SPError(400, f"Role definition {rid} does not exist")
        if not any(u["Id"] == pid for u in self.site.site_users.values()):
            raise SPError(400, f"Principal {pid} is not a user or group of this site (call ensureuser first)")
        if not f.unique_permissions:
            raise SPError(400, "This object inherits permissions: break inheritance before adding a role assignment")
        if (pid, rid) not in f.role_assignments:
            f.role_assignments.append((pid, rid))
        self.site._log()
        return 200, None

    def entity_type(self, g, h, body, verb):
        from .site import SPError
        sp = self.site.lists.get(g["title"])
        if sp is None:
            raise SPError(404, f"List '{g['title']}' does not exist")
        return 200, {"ListItemEntityTypeFullName": sp.entity_type}

    def merge_item(self, g, h, body, verb):
        from .site import SPError
        if verb != "MERGE":
            raise SPError(400, f"This fake only implements MERGE on list items, got {verb}")
        sp = self.site.lists.get(g["title"])
        if sp is None:
            raise SPError(404, f"List '{g['title']}' does not exist")
        item_id = int(g["id"])
        if item_id not in sp.items:
            raise SPError(404, "Item does not exist")
        body = dict(body or {})
        meta = body.pop("__metadata", {})
        if meta.get("type") != sp.entity_type:
            # Learn: ListItemEntityTypeFullName "must be passed as the type property in the metadata"
            raise SPError(400, f"A type named '{meta.get('type')}' could not be resolved by the model; "
                               f"expected {sp.entity_type}")
        etag = h.get("if-match")
        current = f"\"{len(sp.items[item_id].versions)}\""
        if etag not in (None, "*") and etag != current:
            raise SPError(412, "The version of the item has changed (ETag mismatch)")
        # MERGE: only the properties sent change; everything else keeps its value.
        self.site._write(sp, item_id, body, self.site.connection_user)
        return 204, None


def _json(body):
    if body is None or body == "":
        return None
    if isinstance(body, (dict, list)):
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        from .site import SPError
        raise SPError(400, f"Request body isn't valid JSON: {e}") from None
