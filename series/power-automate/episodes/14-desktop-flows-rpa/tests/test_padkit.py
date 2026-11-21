"""The desktop flow text and its contract against the cloud flow that calls it."""
import copy

from padkit.contract import check_cloud_flow, check_input_size
from padkit.lint import lint_script


def codes(findings):
    return sorted(f.code for f in findings)


def test_the_cloud_flow_matches_the_contract(flow, contract):
    assert check_cloud_flow(flow, contract) == []


def test_the_desktop_flow_text_is_clean(script_text, contract):
    assert lint_script(script_text, contract) == []
    assert lint_script(script_text, contract, "unattended") == []


def run_params(flow):
    return flow["properties"]["definition"]["actions"]["Try"]["actions"]["Run_desktop_flow"]["inputs"]["parameters"]


def test_a_missing_required_input_is_an_error(flow, contract):
    del run_params(flow)["item/Amount"]
    (f,) = check_cloud_flow(flow, contract)
    assert f.code == "PAD102" and "Amount" in f.message


def test_an_input_the_desktop_flow_does_not_declare(flow, contract):
    run_params(flow)["item/Currency"] = "EUR"
    assert codes(check_cloud_flow(flow, contract)) == ["PAD103"]


def test_reading_an_undeclared_output(flow, contract):
    flow["properties"]["definition"]["actions"]["Order_saved"]["actions"]["Mark_entered"]["inputs"]["parameters"]["item/PONumber"] = \
        "@outputs('Run_desktop_flow')?['body/PurchaseOrderNumber']"
    (f,) = check_cloud_flow(flow, contract)
    assert f.code == "PAD107" and "PurchaseOrderNumber" in f.message


def test_run_mode_must_be_attended_or_unattended(flow, contract):
    run_params(flow)["runMode"] = "background"
    assert "PAD104" in codes(check_cloud_flow(flow, contract))


def test_no_timeout_and_no_failure_path_are_warnings(flow, contract):
    del flow["properties"]["definition"]["actions"]["Try"]["actions"]["Run_desktop_flow"]["limit"]
    del flow["properties"]["definition"]["actions"]["Catch"]
    flow["properties"]["definition"]["actions"]["Result"]["runAfter"].pop("Catch")
    f = check_cloud_flow(flow, contract)
    assert codes(f) == ["PAD106", "PAD108"] and {x.level for x in f} == {"warning"}


def test_inputs_over_2_mb(contract):
    assert check_input_size({"Supplier": "x" * 100}) == []
    assert codes(check_input_size({"Supplier": "x" * (2 * 1024 * 1024)})) == ["PAD109"]


def test_an_output_that_is_never_assigned(script_text, contract):
    broken = script_text.replace("SET OrderNumber TO Confirm.orderNo", "").replace("SET OrderNumber TO $''''''", "")
    (f,) = lint_script(broken, contract)
    assert f.code == "PAD001" and "OrderNumber" in f.message


def test_a_hard_coded_secret(script_text, contract):
    bad = script_text + "\nSET LegacyPassword TO $'''Winter2026!'''\n"
    (f,) = lint_script(bad, contract)
    assert f.code == "PAD002"
    assert lint_script(script_text + "\nSET LegacyPassword TO $'''%PasswordFromVault%'''\n", contract) == []


def test_free_text_pasted_into_script_text(script_text, contract):
    """The mistake our flow avoids: -Supplier '%Supplier%' inside the PowerShell action."""
    bad = script_text.replace('-InputDir "C:\\MGLab\\run"\'\'\' ScriptOutput=> PreflightJson',
                              '-Supplier \'%Supplier%\'\'\'\' ScriptOutput=> PreflightJson')
    assert bad != script_text
    (f,) = lint_script(bad, contract)
    assert f.code == "PAD004" and "Supplier" in f.message


def test_message_dialogs_cannot_run_unattended(script_text, contract):
    bad = script_text + "\nDisplay.ShowMessageDialog.ShowMessage Message: $'''Done''' Title: $'''x'''\n"
    assert lint_script(bad, contract, "attended") == []
    (f,) = lint_script(bad, contract, "unattended")
    assert f.code == "PAD003"
