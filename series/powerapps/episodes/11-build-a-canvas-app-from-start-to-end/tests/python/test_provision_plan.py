"""The provisioning script's -PlanOnly output agrees with the schema (the Pester tests cover the request bodies and ordering)."""
from conftest import SCRIPTS, run


def plan():
    r = run("pwsh", "-NoProfile", "-NonInteractive", "-File", SCRIPTS / "Provision-ContosoInspections.ps1",
            "-EnvironmentUrl", "https://contoso-dev.crm4.dynamics.com", "-PlanOnly")
    assert r.code == 0, r
    return r.out


def test_the_plan_lists_every_table_column_and_relationship_in_the_schema(schema):
    out = plan()
    for t in schema["tables"]:
        assert t["schemaName"].lower() in out
        for c in t["columns"]:
            assert c["schemaName"] in out, c["schemaName"]
    for r in schema["relationships"]:
        assert r["schemaName"] in out


def test_the_plan_sends_nothing_and_names_the_role_and_publish_steps(schema):
    out = plan()
    assert "nothing is sent" in out
    assert schema["securityRole"]["name"] in out
    assert "PublishAllXml" in out


def test_the_script_never_signs_in():
    text = (SCRIPTS / "Provision-ContosoInspections.ps1").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", ".", "$env:")))
    for forbidden in ("Connect-AzAccount", "az login", "pac auth", "Add-PowerAppsAccount", "Get-Credential"):
        assert forbidden not in code
