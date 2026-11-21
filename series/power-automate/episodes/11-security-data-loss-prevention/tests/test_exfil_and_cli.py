"""The email-recipient rule, and the command line."""
import json
import subprocess
import sys

from conftest import FLOWS, POLICY, SRC

from dlpkit.exfil import external_recipients
from flowkit.lint import load_flow


def run(*args):
    return subprocess.run([sys.executable, "-m", "dlpkit", *args], cwd=SRC, capture_output=True, text=True, timeout=60)


def test_external_literal_recipient_is_a_warning():
    warns, unchecked = external_recipients(load_flow(FLOWS / "request-external-copy.json"), {"contoso.com"})
    assert len(warns) == 1 and "reports@fabrikam.example" in warns[0].message and warns[0].level == "warning"
    assert unchecked == []


def test_subdomains_of_an_allowed_domain_are_internal_and_lookalikes_are_not():
    flow = json.loads((FLOWS / "request-external-copy.json").read_text())
    params = flow["properties"]["definition"]["actions"]["Send_copy_to_partner"]["inputs"]["parameters"]
    params["emailMessage/To"] = "a@eu.contoso.com"
    params["emailMessage/Cc"] = "b@notcontoso.com"
    warns, _ = external_recipients(flow, {"contoso.com"})
    assert [w.message.split()[3].rstrip(",") for w in warns] == ["b@notcontoso.com"]


def test_recipients_from_expressions_are_listed_as_not_checked_never_as_safe():
    warns, unchecked = external_recipients(load_flow(FLOWS / "acknowledge-it-request.json"), {"contoso.com"})
    assert warns == [] and unchecked == ["Send_acknowledgement: emailMessage/To comes from an expression"]


def test_an_address_inside_an_interpolation_is_not_read_as_literal():
    flow = json.loads((FLOWS / "request-external-copy.json").read_text())
    p = flow["properties"]["definition"]["actions"]["Send_copy_to_partner"]["inputs"]["parameters"]
    p["emailMessage/To"] = "@{triggerBody()?['Author']?['Email']};team@contoso.com"
    assert external_recipients(flow, {"contoso.com"})[0] == []


def test_cli_exit_codes_and_output():
    r = run("check", "flows", "--policy", "policy/it-dev.json", "--environment", "dev")
    assert r.returncode == 1
    assert "SUSPENDED  request-asset-lookup.json" in r.stdout and "OK         acknowledge-it-request.json" in r.stdout
    assert r.stdout.strip().endswith("2 flow(s) would be suspended")
    ok = run("check", "flows/acknowledge-it-request.json", "--policy", "policy/it-dev.json")
    assert ok.returncode == 0


def test_cli_what_if_and_strict():
    r = run("check", "flows/request-asset-lookup.json", "--policy", "policy/it-dev.json", "--what-if", "http=Business")
    assert r.returncode == 0
    s = run("check", "flows/request-external-copy.json", "--policy", "policy/it-dev.json", "--allowed-domain", "contoso.com")
    assert s.returncode == 0 and "WARNING" in s.stdout
    assert run("check", "flows/request-external-copy.json", "--policy", "policy/it-dev.json",
               "--allowed-domain", "contoso.com", "--strict").returncode == 1


def test_cli_show_and_bad_policy():
    r = run("show", "policy/it-dev.json")
    assert r.returncode == 0 and "Business" in r.stdout and "SharePoint" in r.stdout
    bad = run("check", "flows", "--policy", "does-not-exist.json")
    assert bad.returncode == 2 and "Can't read the policy" in bad.stdout


def test_cli_groups_reproduces_the_shape_of_the_learn_example(tmp_path):
    pol = {"displayName": "A", "connectorGroups": [{"classification": "Confidential", "connectors": [{"id": "shared_a"}, {"id": "shared_b"}]}]}
    f = tmp_path / "a.json"
    f.write_text(json.dumps(pol))
    r = run("groups", "--policy", str(f), "shared_a", "shared_b", "shared_c")
    assert r.stdout.splitlines() == ["group 1: shared_a, shared_b", "group 2: shared_c"]


def test_flows_in_the_folder_are_the_ones_the_builder_writes():
    """src/flows is generated: re-running the builder must not change it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_flows", SRC / "tools" / "build_flows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, body in mod.FLOWS.items():
        assert json.loads((FLOWS / name).read_text()) == body


def test_demo_flows_pass_flowkit_lint():
    from flowkit.lint import lint
    for f in FLOWS.glob("*.json"):
        assert [x for x in lint(load_flow(f)) if x.level == "error"] == [], f.name
