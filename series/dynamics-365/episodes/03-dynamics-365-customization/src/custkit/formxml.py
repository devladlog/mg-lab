"""Register a form library and an OnLoad handler in a main form's FormXml, idempotently.

This is what the form designer does when you add a library and an event handler on the Events tab. Doing it in
code makes it repeatable across environments and reviewable in a pull request. Element and attribute names follow
the Form XML schema on Learn: <formLibraries><Library name libraryUniqueId/>, and
<events><event name application active><Handlers><Handler functionName libraryName handlerUniqueId enabled
passExecutionContext parameters/></Handlers></event></events>, both direct children of <form>.

Learn also documents updating `systemforms.formxml` with PATCH and then calling PublishXml (Field Service
troubleshooting article "Form context for internal handlers is missing"), which is the path custkit uses.
"""
from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Set

# Deterministic ids: the same library/handler always gets the same GUID, so re-running produces no diff.
_NS = uuid.UUID("00000000-0000-0000-0000-000000000000")


def stable_guid(*parts: str) -> str:
    return "{" + str(uuid.uuid5(_NS, "|".join(parts))) + "}"


@dataclass
class PatchResult:
    xml: str
    changed: bool
    actions: List[str] = field(default_factory=list)


def _form_root(root: ET.Element) -> ET.Element:
    """systemforms.formxml is '<form>...</form>'; a customizations.xml export wraps it in <systemform><form>."""
    if root.tag == "form":
        return root
    found = root.find(".//form")
    if found is None:
        raise ValueError("no <form> element in the form XML")
    return found


def register_onload(formxml: str, library: str, function: str) -> PatchResult:
    """Ensure `library` is a form library and `function` is an enabled OnLoad handler passing the execution context."""
    root = ET.fromstring(formxml)
    form = _form_root(root)
    actions: List[str] = []

    libs = form.find("formLibraries")
    if libs is None:
        libs = ET.SubElement(form, "formLibraries")
    if not any(lib.get("name") == library for lib in libs.findall("Library")):
        if len(libs.findall("Library")) >= 50:   # schema: maxOccurs 50
            raise ValueError("a form can reference at most 50 libraries")
        ET.SubElement(libs, "Library", {"name": library, "libraryUniqueId": stable_guid("lib", library)})
        actions.append(f"added library {library}")

    events = form.find("events")
    if events is None:
        events = ET.SubElement(form, "events")
    onload = next((e for e in events.findall("event") if e.get("name") == "onload"), None)
    if onload is None:
        onload = ET.SubElement(events, "event", {"name": "onload", "application": "false", "active": "false"})
    handlers = onload.find("Handlers")
    if handlers is None:
        handlers = ET.SubElement(onload, "Handlers")

    existing = next((h for h in handlers.findall("Handler")
                     if h.get("functionName") == function and h.get("libraryName") == library), None)
    if existing is None:
        ET.SubElement(handlers, "Handler", {
            "functionName": function, "libraryName": library,
            "handlerUniqueId": stable_guid("onload", library, function),
            "enabled": "true", "parameters": "", "passExecutionContext": "true"})
        actions.append(f"added OnLoad handler {function}")
    else:
        # The classic mistake: handler registered without "Pass execution context as first parameter".
        for attr, want in (("enabled", "true"), ("passExecutionContext", "true")):
            if existing.get(attr) != want:
                existing.set(attr, want)
                actions.append(f"set {attr}=true on {function}")

    if not actions:
        return PatchResult(formxml, False, [])
    return PatchResult(ET.tostring(root, encoding="unicode"), True, actions)


def unregister(formxml: str, library: str) -> PatchResult:
    """Tear-down: remove every handler that uses `library`, then the library itself."""
    root = ET.fromstring(formxml)
    form = _form_root(root)
    actions: List[str] = []
    for handlers in form.iter("Handlers"):
        for h in list(handlers.findall("Handler")):
            if h.get("libraryName") == library:
                handlers.remove(h)
                actions.append(f"removed handler {h.get('functionName')}")
    # Don't leave empty shells behind: the schema wants at least one <event> inside <events>.
    events = form.find("events")
    if events is not None and actions:
        for ev in list(events.findall("event")):
            hs = ev.find("Handlers")
            if hs is not None and not hs.findall("Handler"):
                ev.remove(hs)
            if ev.get("name") == "onload" and len(ev) == 0:
                events.remove(ev)
        if not events.findall("event"):
            form.remove(events)
    libs = form.find("formLibraries")
    if libs is not None:
        for lib in list(libs.findall("Library")):
            if lib.get("name") == library:
                libs.remove(lib)
                actions.append(f"removed library {library}")
        if not libs.findall("Library"):
            form.remove(libs)        # schema: a formLibraries element needs at least one Library
    if not actions:
        return PatchResult(formxml, False, [])
    return PatchResult(ET.tostring(root, encoding="unicode"), True, actions)


def fields_on_form(formxml: str) -> Set[str]:
    """Logical names bound to a control (datafieldname) anywhere on the form, including the header."""
    form = _form_root(ET.fromstring(formxml))
    return {c.get("datafieldname") for c in form.iter("control") if c.get("datafieldname")}


def missing_fields(formxml: str, required: List[str]) -> List[str]:
    """Columns the rule/script needs that aren't on the form.

    Learn: a business rule doesn't fire on a form when a column it references isn't on that form, and a
    script only sees columns that are on the form or declared as web resource dependencies.
    """
    present = fields_on_form(formxml)
    return [f for f in required if f not in present]
