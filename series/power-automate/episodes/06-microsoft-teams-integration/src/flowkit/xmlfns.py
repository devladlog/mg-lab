"""xml() and a subset of xpath() for the flowkit evaluator.

xml() follows the reference: the JSON object "must have only one root property, which can't be an
array"; an array property becomes repeated elements (Example 4, options 1-4). xpath() supports what
the reference examples and our flows use: absolute and '//' location paths, ElementTree predicates
([n], [last()], [@attr], [@attr='v'], [child='v']), a trailing /text(), and the sum(), count(),
string() and number() functions. Anything else raises instead of guessing.

References:
  https://learn.microsoft.com/azure/logic-apps/expression-functions-reference#xml
  https://learn.microsoft.com/azure/logic-apps/expression-functions-reference#xpath
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")


class XmlError(ValueError):
    pass


class XmlValue:
    """The result of xml(): wraps an ElementTree element."""

    def __init__(self, element: ET.Element):
        self.element = element

    def __str__(self) -> str:
        return ET.tostring(self.element, encoding="unicode")

    def __repr__(self) -> str:
        return f"XmlValue({self})"

    def __eq__(self, other) -> bool:
        return str(self) == str(other)


def _scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _fill(el: ET.Element, value) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith("@"):
                el.set(_check_name(key[1:]), _scalar(child))
            elif key == "#text":
                el.text = _scalar(child)
            else:
                _append(el, key, child)
    elif isinstance(value, list):
        raise XmlError("an array can't be converted directly; wrap it in an object property")
    else:
        el.text = _scalar(value)


def _append(parent: ET.Element, key: str, value) -> None:
    name = _check_name(key)
    items = value if isinstance(value, list) else [value]
    for item in items:  # an array property becomes repeated elements with the same name
        if isinstance(item, list):
            raise XmlError(f"nested arrays under {key!r} can't be converted to XML")
        _fill(ET.SubElement(parent, name), item)


def _check_name(key: str) -> str:
    if not _NAME_RE.match(key) or key.lower().startswith("xml"):
        raise XmlError(f"{key!r} isn't a valid XML element name (spaces and most punctuation aren't allowed); "
                       f"use camelCase property names before calling xml()")
    return key


def to_xml(value) -> XmlValue:
    if isinstance(value, XmlValue):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("<"):
            try:
                return XmlValue(ET.fromstring(text))
            except ET.ParseError as e:
                raise XmlError(f"not valid XML: {e}") from e
        try:
            value = json.loads(text)
        except json.JSONDecodeError as e:
            raise XmlError(f"xml() expects XML or a JSON object string: {e}") from e
    if not isinstance(value, dict):
        raise XmlError(f"xml() expects an object with one root property, got {type(value).__name__}")
    keys = [k for k in value if k != "?xml"]
    if len(keys) != 1:
        raise XmlError(f"the JSON object must have only one root property, found {keys}")
    root_name = keys[0]
    if isinstance(value[root_name], list):
        raise XmlError("the root property can't be an array (wrap it: {\"root\": {\"item\": [...]}})")
    root = ET.Element(_check_name(root_name))
    _fill(root, value[root_name])
    return XmlValue(root)


_FN_RE = re.compile(r"^\s*(sum|count|string|number)\((.*)\)\s*$", re.S)


def _select(root: ET.Element, path: str) -> list:
    path = path.strip()
    want_text = path.endswith("/text()")
    if want_text:
        path = path[: -len("/text()")]
    doc = ET.Element("_document")  # a document node above the root, so '/root/...' and '//x' work
    doc.append(root)
    try:
        if path.startswith("//"):
            matches = doc.findall(".//" + path[2:])
        elif path.startswith("/"):
            matches = doc.findall("./" + path[1:])
        else:
            matches = root.findall("./" + path)
    except SyntaxError as e:
        raise XmlError(f"flowkit's XPath subset doesn't support {path!r}: {e}") from e
    if want_text:
        return [m.text or "" for m in matches]
    return matches


def _number(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        raise XmlError(f"{text!r} isn't a number (XPath would return NaN; flowkit refuses)") from None


def xpath(xml_value, expression: str):
    if not isinstance(expression, str):
        raise XmlError("xpath() expects the XPath expression as a string")
    root = to_xml(xml_value).element
    m = _FN_RE.match(expression)
    if m:
        fn, inner = m.groups()
        nodes = _select(root, inner)
        texts = [n if isinstance(n, str) else "".join(n.itertext()) for n in nodes]
        if fn == "sum":
            return float(sum(_number(t) for t in texts))
        if fn == "count":
            return float(len(texts))
        if fn == "string":
            return texts[0] if texts else ""
        return _number(texts[0]) if texts else float("nan")
    nodes = _select(root, expression)
    values = [n if isinstance(n, str) else XmlValue(n) for n in nodes]
    if len(values) == 1:
        return values[0]
    return values
