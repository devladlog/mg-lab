"""The agent: instructions, topic, agent flow, knowledge sources and checklists, all checked against the shared ContosoInspections schema."""
import json
import re
import zipfile

import docx
import yaml

from build_workflow import build
from conftest import SRC, column, table

AGENT = SRC / "agent"
FLOW = AGENT / "workflows" / "CreateFinding" / "workflow.json"
ZERO = "00000000-0000-0000-0000-000000000000"


def labels(schema, tname, cname):
    return [o[0] for o in column(schema, tname, cname)["options"]]


def test_instructions_name_every_severity_and_category_and_refuse_write_powers(schema):
    text = (AGENT / "instructions.md").read_text(encoding="utf-8")
    for label in labels(schema, "cin_inspectionitem", "cin_severity") + labels(schema, "cin_inspectionitem", "cin_category"):
        assert label in text
    assert len(text) < 3000
    assert "wait for a yes" in text
    assert "cannot approve, reject or delete" in text
    assert "reviewer notes" in text.lower()


def test_topic_is_a_valid_adaptive_dialog_with_five_to_ten_trigger_phrases():
    topic = yaml.safe_load((AGENT / "topics" / "log-a-finding.mcs.yml").read_text(encoding="utf-8"))
    assert topic["kind"] == "AdaptiveDialog"
    begin = topic["beginDialog"]
    assert begin["kind"] == "OnRecognizedIntent"
    assert 5 <= len(begin["intent"]["triggerQueries"]) <= 10  # Learn: 5 to 10 trigger phrases
    ids = []

    def walk(nodes):
        for n in nodes:
            ids.append(n["id"])
            for c in n.get("conditions", []):
                walk(c["actions"])
            walk(n.get("elseActions", []))
    walk(begin["actions"])
    assert len(ids) == len(set(ids))


def test_topic_asks_for_a_yes_before_it_calls_the_flow():
    topic = yaml.safe_load((AGENT / "topics" / "log-a-finding.mcs.yml").read_text(encoding="utf-8"))
    actions = topic["beginDialog"]["actions"]
    kinds = [a["kind"] for a in actions]
    assert kinds.index("Question") < kinds.index("ConditionGroup")
    confirm = next(a for a in actions if a["id"] == "confirm")
    assert confirm["entity"] == "BooleanPrebuiltEntity" and confirm["alwaysPrompt"] is True
    cond = next(a for a in actions if a["kind"] == "ConditionGroup")
    yes = cond["conditions"][0]
    assert yes["condition"] == "=Topic.Confirmed = true"
    assert [a["kind"] for a in yes["actions"]][0] == "InvokeFlowAction"
    assert "Nothing was written" in cond["elseActions"][0]["activity"]


def test_topic_bindings_match_the_flow_trigger_inputs_and_output():
    topic = yaml.safe_load((AGENT / "topics" / "log-a-finding.mcs.yml").read_text(encoding="utf-8"))
    cond = next(a for a in topic["beginDialog"]["actions"] if a["kind"] == "ConditionGroup")
    node = cond["conditions"][0]["actions"][0]
    wf = json.loads(FLOW.read_text(encoding="utf-8"))["properties"]["definition"]
    props = wf["triggers"]["manual"]["inputs"]["schema"]["properties"]
    assert list(node["input"]["binding"]) == list(props)
    assert list(node["output"]["binding"]) == ["result"]
    assert node["flowId"] == ZERO  # a placeholder: Copilot Studio writes the real id when the flow is attached
    # every topic variable the flow gets is asked for by a Question
    asked = {a["variable"].split(":")[1].split(".")[1] for a in topic["beginDialog"]["actions"] if a["kind"] == "Question"}
    used = set(re.findall(r"Topic\.(\w+)", " ".join(node["input"]["binding"].values())))
    assert used <= asked


def test_workflow_json_is_exactly_what_the_generator_writes():
    assert json.loads(FLOW.read_text(encoding="utf-8")) == build()


def collect(node, found):
    if isinstance(node, dict):
        found.append(node)
        for v in node.values():
            collect(v, found)
    elif isinstance(node, list):
        for v in node:
            collect(v, found)
    return found


def test_flow_uses_the_agent_trigger_and_one_response_shape():
    wf = json.loads(FLOW.read_text(encoding="utf-8"))["properties"]["definition"]
    trig = wf["triggers"]["manual"]
    assert (trig["type"], trig["kind"]) == ("Request", "Skills")
    assert set(trig["inputs"]["schema"]["required"]) == set(trig["inputs"]["schema"]["properties"])
    responses = [n for n in collect(wf["actions"], []) if n.get("type") == "Response"]
    assert len(responses) == 5
    assert all(r["kind"] == "Skills" for r in responses)
    # Learn: the response action can be used in several branches but must have the same outputs in each
    assert len({json.dumps(r["inputs"]["schema"], sort_keys=True) for r in responses}) == 1
    assert "asynchronous" not in json.dumps(wf).lower()


def test_flow_writes_only_real_schema_columns_with_schema_option_values(schema):
    wf = json.loads(FLOW.read_text(encoding="utf-8"))["properties"]["definition"]
    creates = [n for n in collect(wf["actions"], []) if n.get("inputs", {}).get("host", {}).get("operationId") == "CreateRecord"]
    (create,) = creates
    p = create["inputs"]["parameters"]
    assert p["entityName"] == "cin_inspectionitems"
    cols = {k.split("/")[1].split("@")[0] for k in p if k.startswith("item/")}
    item_cols = {c["logicalName"] for c in table(schema, "cin_inspectionitem")["columns"]} | {"cin_name"}
    assert cols <= item_cols
    assert p["item/cin_passed"] is False  # an agent-logged finding is a failed check
    assert p["item/cin_notes"].startswith("@concat('[Agent] '")
    assert "cin_inspections(" in p["item/cin_inspectionid@odata.bind"]
    prefix = schema["publisher"]["optionValuePrefix"] * 10000
    for key, col in (("item/cin_severity", "cin_severity"), ("item/cin_category", "cin_category")):
        mapping = json.loads(re.search(r"json\('(.+?)'\)", p[key]).group(1))
        assert mapping == {label: prefix + value for label, value in column(schema, "cin_inspectionitem", col)["options"]}


def test_flow_refuses_closed_inspections_and_escapes_the_filter(schema):
    text = FLOW.read_text(encoding="utf-8")
    status = dict(column(schema, "cin_inspection", "cin_status")["options"])
    prefix = schema["publisher"]["optionValuePrefix"] * 10000
    assert f"createArray({prefix + status['Approved']},{prefix + status['Rejected']})" in text
    wf = json.loads(text)["properties"]["definition"]
    flt = wf["actions"]["Find_inspection"]["inputs"]["parameters"]["$filter"]
    assert "replace(triggerBody()?['text'],'''','''''')" in flt  # OData: a single quote is doubled


def test_knowledge_sources_follow_learns_limits_and_the_schema(schema):
    k = json.loads((AGENT / "knowledge.json").read_text(encoding="utf-8"))
    dv = k["dataverse"]
    assert 1 <= len(dv["tables"]) <= 15  # Learn: up to 15 tables per Dataverse knowledge source
    assert all(t in {x["logicalName"] for x in schema["tables"]} for t in dv["tables"])
    assert "cin_inspector" not in dv["tables"]
    secured = [c["logicalName"] for t in schema["tables"] for c in t["columns"] if c.get("secured")]
    assert secured == ["cin_reviewernotes"] and "cin_inspection.cin_reviewernotes" in dv["excludedColumns"]
    assert dv["authentication"].startswith("Authenticate with Microsoft")  # Learn: the only mode Dataverse knowledge supports
    assert dv["description"] and k["sharepoint"]["description"]


def test_column_descriptions_only_describe_real_columns(schema):
    d = json.loads((SRC / "data" / "column-descriptions.json").read_text(encoding="utf-8"))
    for t, cols in d.items():
        for c, text in cols.items():
            column(schema, t, c)
            assert 10 < len(text) < 200
    assert "cin_reviewernotes" not in json.dumps(d)


def test_checklists_build_into_real_word_files_with_the_severity_words(schema, tmp_path):
    import build_checklists
    names = json.loads((AGENT / "knowledge.json").read_text(encoding="utf-8"))["sharepoint"]["files"]
    assert build_checklists.build(tmp_path) == sorted(names)
    assert not list((SRC / "checklists").glob("*.docx")), "no binaries in the repo"
    sev = labels(schema, "cin_inspectionitem", "cin_severity")
    for n in names:
        path = tmp_path / n
        assert zipfile.is_zipfile(path)
        text = "\n".join(p.text for p in docx.Document(path).paragraphs)
        assert any(s in text for s in sev if s != "Info"), n
        assert "fictional" in text
