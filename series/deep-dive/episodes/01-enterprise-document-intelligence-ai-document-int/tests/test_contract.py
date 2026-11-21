"""Function, library and flow must agree on one contract (src/docintel/columns.json)."""
import json
import re
from pathlib import Path

from docintel.contract import COLUMNS, STATUS_CHOICES
from docintel.mapping import extract
from docintel.rules import decide

ROOT = Path(__file__).resolve().parents[1]
FLOW = json.loads((ROOT / "flow" / "definition.json").read_text(encoding="utf-8"))
ACTIONS = FLOW["actions"]
TRIGGERS = FLOW["triggers"]


def params_of(action):
    inputs = action.get("inputs")
    return inputs.get("parameters", {}) if isinstance(inputs, dict) else {}


def op_of(action):
    inputs = action.get("inputs")
    return inputs.get("host", {}).get("operationId") if isinstance(inputs, dict) else None


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def test_function_returns_every_column_and_nothing_else(invoice_result):
    assert set(decide(extract(invoice_result)).columns) == set(COLUMNS)


def test_flow_writes_only_columns_that_exist():
    written = set()
    for a in ACTIONS.values():
        if op_of(a) == "PatchFileItem":
            for k in params_of(a):
                if k.startswith("item/"):
                    written.add(k.split("/")[1])
    assert written and written <= set(COLUMNS)
    # the main update writes every column (status and reasons included)
    main = {k.split("/")[1] for k in ACTIONS["Update_file_properties"]["inputs"]["parameters"] if k.startswith("item/")}
    assert main == set(COLUMNS)


def test_flow_reads_only_fields_the_function_returns():
    read = {m for s in strings(FLOW) for m in re.findall(r"\['fields'\]\?\['(\w+)'\]", s)}
    assert read and read <= set(COLUMNS)


def test_choice_columns_are_written_through_value_and_with_known_choices():
    for name, a in ACTIONS.items():
        params = params_of(a)
        assert "item/InvStatus" not in params, f"{name}: a Choice column is set via item/InvStatus/Value"
        literal = params.get("item/InvStatus/Value")
        if literal and not literal.startswith("@"):
            assert literal in STATUS_CHOICES
    for s in strings(FLOW):
        for lit in re.findall(r"'(Ready|Needs review|Rejected|Pending)'", s):
            assert lit in STATUS_CHOICES


def test_every_reference_points_to_an_existing_action():
    names = set(ACTIONS)
    for name, a in ACTIONS.items():
        assert set(a.get("runAfter", {})) <= names, f"{name} runs after an unknown action"
    for s in strings(FLOW):
        for ref in re.findall(r"(?:body|outputs|actions)\('([^']+)'\)", s):
            assert ref in names, f"unknown action referenced: {ref}"


def test_run_after_graph_has_no_cycles_and_one_start():
    starts = [n for n, a in ACTIONS.items() if not a.get("runAfter")]
    assert starts == ["Get_API_key"]
    seen, order = set(), []

    def visit(n, path=()):
        assert n not in path, f"cycle: {path + (n,)}"
        for p in ACTIONS[n].get("runAfter", {}):
            visit(p, path + (n,))
        if n not in seen:
            seen.add(n)
            order.append(n)

    for n in ACTIONS:
        visit(n)
    assert len(order) == len(ACTIONS)


def test_trigger_is_created_only_so_our_own_update_does_not_retrigger():
    (trigger,) = TRIGGERS.values()
    # 'When a file is created or modified (properties only)' would fire again on our Update file properties
    assert trigger["inputs"]["host"]["operationId"] == "GetOnNewFileItems"


def test_secrets_never_show_in_run_history():
    assert ACTIONS["Get_API_key"]["runtimeConfiguration"]["secureData"]["properties"] == ["inputs", "outputs"]
    assert "inputs" in ACTIONS["Extract_invoice"]["runtimeConfiguration"]["secureData"]["properties"]
    flat = json.dumps(FLOW)
    assert "x-functions-key\": \"@outputs('Get_API_key')" in flat      # the key comes from Key Vault, not a literal


def test_failure_branch_marks_the_file_for_review():
    a = ACTIONS["Mark_extraction_failed"]
    assert a["runAfter"] == {"Extract_invoice": ["Failed", "TimedOut"]}
    assert a["inputs"]["parameters"]["item/InvStatus/Value"] == "Needs review"


def test_flow_retries_a_little_because_the_sdk_already_retries():
    rp = ACTIONS["Extract_invoice"]["inputs"]["retryPolicy"]
    assert rp["type"] == "exponential" and rp["count"] <= 2


def test_no_real_identifiers_in_the_flow():
    flat = json.dumps(FLOW)
    for guid in re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", flat, re.I):
        assert guid == "00000000-0000-0000-0000-000000000000"
    hosts = set(re.findall(r"https://([a-z0-9.-]+)", flat))
    assert all(h.startswith(("contoso.", "func-contoso", "schema.management.azure.com")) for h in hosts), hosts
