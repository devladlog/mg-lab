"""Render a column or view format for one row into a small, comparable tree (no HTML, no browser)."""
from __future__ import annotations

from .expr import Context, NotSupportedLocally, evaluate, to_ast, to_string


def _value(v, ctx: Context):
    return to_string(evaluate(to_ast(v), ctx))


def render_element(elm: dict, ctx: Context) -> dict:
    if "forEach" in elm or "columnFormatterReference" in elm:
        raise NotSupportedLocally("forEach / columnFormatterReference")
    node = {"elm": elm.get("elmType", "div")}
    if "txtContent" in elm:
        node["text"] = _value(elm["txtContent"], ctx)
    attrs = {k: _value(v, ctx) for k, v in elm.get("attributes", {}).items()}
    if attrs:
        node["attrs"] = attrs
    style = {k: _value(v, ctx) for k, v in elm.get("style", {}).items()}
    if style:
        node["style"] = style
    # Learn: "If an element has the txtContent property, the child properties are ignored."
    if "txtContent" not in elm and elm.get("children"):
        node["children"] = [render_element(c, ctx) for c in elm["children"]]
    return node


def render_column(fmt: dict, field: str, row: dict, **ctx_args) -> dict:
    """Render a column format for `field` in `row` (row holds only the fields that are in the view)."""
    return render_element(fmt, Context(row=row, current_field=field, **ctx_args))


def render_view(fmt: dict, row: dict, **ctx_args) -> dict:
    """Render a view format. In a view format @currentField means Title, as documented on Learn."""
    ctx = Context(row=row, current_field="Title", **ctx_args)
    out = {}
    if "additionalRowClass" in fmt:
        out["additionalRowClass"] = _value(fmt["additionalRowClass"], ctx)
    if "rowFormatter" in fmt:
        out["rowFormatter"] = render_element(fmt["rowFormatter"], ctx)
    return out


def classes(node: dict) -> set[str]:
    """All classes in a rendered tree."""
    found = set(node.get("attrs", {}).get("class", "").split())
    for c in node.get("children", []):
        found |= classes(c)
    return found


def texts(node: dict) -> list[str]:
    out = [node["text"]] if node.get("text") else []
    for c in node.get("children", []):
        out += texts(c)
    return out
