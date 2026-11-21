import json
from pathlib import Path

import alm_check
from conftest import MODEL, REPORT, STAGES

STAGES_JSON = json.loads(STAGES.read_text(encoding="utf-8"))


def rules(findings):
    return [f["rule"] for f in findings]


def run(model_dir, **kw):
    return alm_check.check(alm_check.read_model(model_dir), kw.get("report"), kw.get("stages"))


def test_the_project_is_clean_apart_from_the_pbir_note():
    f = run(MODEL, report=REPORT, stages=STAGES_JSON)
    assert rules(f) == ["AL007"] and f[0]["severity"] == "info"


def test_pbir_note_only_when_the_report_is_pbir(tmp_path):
    (tmp_path / "report.json").write_text("{}", encoding="utf-8")
    assert run(MODEL, report=tmp_path) == []


def test_parameters_are_read_with_type_and_value():
    p = alm_check.read_model(MODEL)["parameters"]
    assert set(p) == {"ExportSite", "ExportsFolder", "StageName"}
    assert all(v["type"] == "Text" for v in p.values())
    assert p["StageName"]["value"] == '"DEV"'


def test_AL003_rules_on_the_development_stage():
    stages = json.loads(json.dumps(STAGES_JSON))
    stages["stages"][0]["parameterRules"] = {"StageName": "DEV"}
    assert "AL003" in rules(run(MODEL, stages=stages))


def test_AL002_rule_for_a_parameter_the_model_does_not_have():
    stages = json.loads(json.dumps(STAGES_JSON))
    stages["stages"][1]["parameterRules"]["ExportFolder"] = "exports"          # typo: no s
    f = [x for x in run(MODEL, stages=stages) if x["rule"] == "AL002"]
    assert len(f) == 1 and "'ExportFolder'" in f[0]["message"]


def test_AL001_parameter_that_is_not_text(model_copy):
    exp = model_copy / "expressions.tmdl"
    exp.write_text(exp.read_text(encoding="utf-8").replace('"exports-sample" meta [IsParameterQuery=true, Type="Text"',
                                                           '3 meta [IsParameterQuery=true, Type="Number"'), encoding="utf-8")
    f = [x for x in run(model_copy, stages=STAGES_JSON) if x["rule"] == "AL001"]
    assert len(f) == 2 and all("ExportsFolder" in x["message"] and "Number" in x["message"] for x in f)


def test_AL004_address_typed_into_the_m(model_copy):
    sales = model_copy / "tables" / "Sales.tmdl"
    sales.write_text(sales.read_text(encoding="utf-8").replace("SharePoint.Files(ExportSite,",
                                                               'SharePoint.Files("https://contoso.sharepoint.com/sites/ContosoBikesData",'), encoding="utf-8")
    f = run(model_copy)
    assert rules(f) == ["AL004"] and "ContosoBikesData" in f[0]["message"]


def test_AL005_data_source_rule_on_a_parameterised_source():
    stages = json.loads(json.dumps(STAGES_JSON))
    stages["stages"][1]["dataSourceRules"] = [{"item": "ContosoSales", "to": "https://contoso.sharepoint.com/sites/Other"}]
    f = [x for x in run(MODEL, stages=stages) if x["rule"] == "AL005"]
    assert len(f) == 1 and "ExportSite" in f[0]["message"]


def test_AL006_dataflow_connector_on_episode_7_model():
    ep7 = MODEL.parents[3] / "07-dataflows-shared-datasets" / "src" / "ContosoSales.SemanticModel" / "definition"
    if not ep7.exists():
        return
    assert "AL006" in rules(run(ep7))


def test_AL006_on_a_synthetic_dataflow_partition(model_copy):
    sales = model_copy / "tables" / "Sales.tmdl"
    sales.write_text(sales.read_text(encoding="utf-8").replace("SharePoint.Files(ExportSite, [ApiVersion = 15])", "PowerPlatform.Dataflows(null)"), encoding="utf-8")
    assert "AL006" in rules(run(model_copy))


def test_AL008_directquery_with_auto_date_time(model_copy):
    (model_copy / "tables" / "LocalDateTable_x.tmdl").write_text("table LocalDateTable_x\n\n\tpartition p = calculated\n\t\tmode: import\n", encoding="utf-8")
    sales = model_copy / "tables" / "Sales.tmdl"
    sales.write_text(sales.read_text(encoding="utf-8").replace("mode: import", "mode: directQuery", 1), encoding="utf-8")
    assert "AL008" in rules(run(model_copy))


def test_rules_sheet_lists_every_stage_rule():
    sheet = alm_check.rules_sheet(alm_check.read_model(MODEL), STAGES_JSON)
    lines = sheet.splitlines()
    assert len(lines) == 2 + 4
    assert "| Test | ContosoSales | Parameter rule | StageName | TEST" in sheet
    assert "| Production | ContosoSales | Parameter rule | ExportsFolder | exports" in sheet


# ---------------------------------------------------------------- diff on incremental refresh tables
def table(name, cols, policy=True, calc=()):
    t = f"table {name}\n\n"
    if policy:
        t += "\trefreshPolicy\n\t\tpolicyType: basic\n\t\trollingWindowGranularity: year\n\t\trollingWindowPeriods: 3\n\t\tincrementalGranularity: day\n\t\tincrementalPeriods: 10\n\n"
    for col, src in cols.items():
        q = f"'{col}'" if " " in col else col
        t += f"\tcolumn {q}\n\t\tdataType: string\n\t\tsourceColumn: {src}\n\n"
    for c in calc:
        t += f"\tcolumn {c} = [A] & \"x\"\n\t\tdataType: string\n\n"
    return t + "\tpartition p = m\n\t\tmode: import\n\t\tsource = let x = 1 in x\n"


def write_model(root: Path, tables: dict):
    (root / "tables").mkdir(parents=True)
    for n, t in tables.items():
        (root / "tables" / f"{n}.tmdl").write_text(t, encoding="utf-8")
    return root


def test_diff_column_rename_on_an_incremental_table(tmp_path):
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"Order Date": "OrderDate", "Amount": "Amount"})})
    new = write_model(tmp_path / "new", {"Sales": table("Sales", {"Order Date": "OrderDate", "Net Amount": "Amount"})})
    f = alm_check.diff(alm_check.read_model(old), alm_check.read_model(new))
    assert rules(f) == ["AL011"] and "'Amount' is renamed to 'Net Amount'" in f[0]["message"]


def test_diff_column_removed_or_added_is_allowed(tmp_path):
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"Order Date": "OrderDate", "Amount": "Amount", "Note": "Note"})})
    new = write_model(tmp_path / "new", {"Sales": table("Sales", {"Order Date": "OrderDate", "Amount": "Amount", "Channel": "Channel"})})
    assert alm_check.diff(alm_check.read_model(old), alm_check.read_model(new)) == []


def test_diff_calculated_column_rename_is_allowed(tmp_path):
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"Order Date": "OrderDate"}, calc=["Flag"])})
    new = write_model(tmp_path / "new", {"Sales": table("Sales", {"Order Date": "OrderDate"}, calc=["Flag2"])})
    assert alm_check.diff(alm_check.read_model(old), alm_check.read_model(new)) == []


def test_diff_table_rename(tmp_path):
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"Order Date": "OrderDate", "Amount": "Amount"})})
    new = write_model(tmp_path / "new", {"Orders": table("Orders", {"Order Date": "OrderDate", "Amount": "Amount"})})
    f = alm_check.diff(alm_check.read_model(old), alm_check.read_model(new))
    assert rules(f) == ["AL010"] and "renamed to 'Orders'" in f[0]["message"]


def test_diff_policy_removed(tmp_path):
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"Order Date": "OrderDate"})})
    new = write_model(tmp_path / "new", {"Sales": table("Sales", {"Order Date": "OrderDate"}, policy=False)})
    assert rules(alm_check.diff(alm_check.read_model(old), alm_check.read_model(new))) == ["AL012"]


def test_diff_ignores_tables_without_a_policy(tmp_path):
    old = write_model(tmp_path / "old", {"Dim": table("Dim", {"A": "A"}, policy=False)})
    new = write_model(tmp_path / "new", {"Dim": table("Dim", {"B": "A"}, policy=False)})
    assert alm_check.diff(alm_check.read_model(old), alm_check.read_model(new)) == []


def test_cli_exit_codes(capsys, tmp_path):
    assert alm_check.main(["check", "--model", str(MODEL), "--report", str(REPORT), "--stages", str(STAGES)]) == 0
    old = write_model(tmp_path / "old", {"Sales": table("Sales", {"A": "A"})})
    new = write_model(tmp_path / "new", {"Sales": table("Sales", {"A": "A"}, policy=False)})
    assert alm_check.main(["diff", str(old), str(new)]) == 1
    assert "AL012" in capsys.readouterr().out
    assert alm_check.main(["rules", "--model", str(MODEL), "--stages", str(STAGES)]) == 0
