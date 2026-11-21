"""The solution's flow, end to end: SharePoint trigger -> List rows -> Select/Filter -> Run script -> CSV + email."""
import pytest

from excelfake import scenario
from excelfake.workbook import ExcelDate, to_serial

from conftest import needs_node

pytestmark = needs_node


@pytest.fixture(scope="module")
def outcome():
    return scenario.run_import()


def row(o, sku):
    return [r for r in o.catalogue_rows() if r[0] == sku]


def test_the_run_succeeds_and_reads_all_400_rows(outcome):
    assert outcome.run.status == "Succeeded"
    assert len(outcome.run.actions["List_price_rows"].outputs["body"]["value"]) == 400
    assert outcome.run.status_of("Stop_not_all_rows_read") == "Skipped"


def test_four_rows_are_rejected_with_a_reason(outcome):
    rejected = {r["sku"]: r["problem"] for r in outcome.run.actions["Rejected_rows"].outputs["body"]}
    assert rejected == {"": "Missing item number", "FAB-0396": "Price is not a number",
                        "FAB-0397": "Price has a comma: use a number cell", "FAB-0398": "Price must be more than zero"}


def test_one_script_call_upserts_everything(outcome):
    r = outcome.result
    assert (r["received"], r["inserted"], r["updated"], r["unchanged"]) == (396, 15, 288, 92)
    assert r["duplicatesInFile"] == 1 and r["duplicateRowsInCatalogue"] == 1
    assert [c["sku"] for c in r["bigChanges"]] == ["FAB-0100", "FAB-0200", "FAB-0300"]
    writes = outcome.run.actions["Upsert_catalogue"].outputs["body"]["writes"]
    assert writes == {"setValues": 1, "addRows": 1}
    assert outcome.excel.calls == ["GetItems", "GetItems", "RunScriptProdV2"]  # two pages of 256, one script


def test_the_catalogue_has_the_new_prices(outcome):
    assert len(outcome.catalogue_rows()) == 381 + 15
    assert row(outcome, "FAB-0005")[0][2] == scenario.new_price(5)
    assert row(outcome, "FAB-0042")[0][2] == round(scenario.new_price(42) - 0.10, 2)  # last row in the file wins
    new = row(outcome, "FAB-0395")[0]
    assert new[2] == scenario.new_price(395) and new[3] == to_serial(scenario.VALID_FROM)
    assert new[4:] == ["Fabrikam", scenario.PRICE_FILE]


def test_a_sku_pasted_twice_in_the_catalogue_is_updated_twice(outcome):
    rows = row(outcome, "FAB-0007")
    assert len(rows) == 2 and rows[0] == rows[1] and rows[0][2] == scenario.new_price(7)


def test_rejected_rows_are_saved_as_csv_next_to_the_file(outcome):
    (path, csv), = outcome.files.items()
    assert path == "/Price lists/Rejected/Fabrikam price list 2026-12-rejected.csv"
    lines = csv.split("\r\n")
    assert lines[0] == "Item No.,Description,Unit price,Valid from,Problem"
    assert 'FAB-0397,"Headset, USB","12,50",2026-12-01,Price has a comma: use a number cell' in lines


def test_purchasing_gets_one_summary_email(outcome):
    (mail,) = outcome.mail
    assert mail["emailMessage/To"] == "purchasing@contoso.com"
    assert mail["emailMessage/Subject"] == "Price list Fabrikam price list 2026-12.xlsx: 288 updated, 15 new, 4 rejected"
    assert "<td>FAB-0200</td>" in mail["emailMessage/Body"] and "400 rows read" in mail["emailMessage/Body"]


def test_the_rejected_csv_does_not_start_a_run():
    from flowkit import Simulator, load_flow
    run = Simulator(load_flow(scenario.FLOW_PATH)).run(scenario.trigger_body("Fabrikam price list 2026-12-rejected.csv"))
    assert run.status == "Skipped"


def test_no_rejected_rows_means_no_csv():
    wb = scenario.price_list()
    wb.tables["Prices"].rows = wb.tables["Prices"].rows[:-4]
    o = scenario.run_import(price_wb=wb)
    assert o.run.status == "Succeeded" and o.files == {} and o.run.status_of("Save_rejected_rows") == "Skipped"
