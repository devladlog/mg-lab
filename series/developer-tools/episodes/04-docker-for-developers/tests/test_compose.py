"""compose.yaml: the official Compose Specification schema, our rules, and the variable interpolation."""
import json
import re

import jsonschema
import pytest
import yaml

from conftest import APP, SCHEMAS, cl


def schema_errors(doc):
    schema = json.loads((SCHEMAS / "compose-spec.json").read_text())
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)]


def interpolate(text: str, env: dict) -> str:
    """The subset of Compose interpolation we use: ${VAR}, ${VAR:?message}, and $$ for a literal $."""
    def sub(m):
        if m.group(0) == "$$":
            return "$"
        name, op, arg = m.group(1), m.group(2) or "", m.group(3) or ""
        value = env.get(name, "")
        if op == ":?" and not value:
            raise ValueError(f"required variable {name} is missing a value: {arg}")
        return value
    return re.sub(r"\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)(:\?)?([^}]*)\}", sub, text)


def test_matches_the_compose_specification(compose):
    assert schema_errors(compose) == []


def test_schema_catches_a_typo(compose):
    broken = json.loads(json.dumps(compose))
    broken["services"]["api"]["depend_on"] = broken["services"]["api"].pop("depends_on")
    assert schema_errors(broken)


def test_our_rules_pass(compose):
    assert cl.lint_compose(compose) == []


def test_missing_password_stops_compose_instead_of_starting_with_an_empty_one():
    raw = (APP / "compose.yaml").read_text()
    with pytest.raises(ValueError, match="MSSQL_SA_PASSWORD is missing a value: set MSSQL_SA_PASSWORD in .env"):
        interpolate(raw, {})


def test_password_reaches_both_services_and_the_healthcheck_reads_the_containers_variable():
    raw = (APP / "compose.yaml").read_text()
    doc = yaml.safe_load(interpolate(raw, {"MSSQL_SA_PASSWORD": "Demo-Passw0rd-only"}))
    api_cs = doc["services"]["api"]["environment"]["ConnectionStrings__Orders"]
    assert api_cs.startswith("Server=db;") and api_cs.endswith("; Password=Demo-Passw0rd-only")
    assert "TrustServerCertificate=True;" in api_cs
    assert doc["services"]["db"]["environment"]["MSSQL_SA_PASSWORD"] == "Demo-Passw0rd-only"
    test = doc["services"]["db"]["healthcheck"]["test"][1]
    assert '-P "$MSSQL_SA_PASSWORD"' in test and "Demo-Passw0rd-only" not in test


def test_csharp_test_uses_the_exact_string_compose_produces():
    raw = (APP / "compose.yaml").read_text()
    doc = yaml.safe_load(interpolate(raw, {"MSSQL_SA_PASSWORD": "Demo-Passw0rd-only"}))
    cs_test = (APP / "tests/Contoso.Orders.Api.Tests/SqlServerModelTests.cs").read_text()
    assert f'"{doc["services"]["api"]["environment"]["ConnectionStrings__Orders"]}"' in cs_test


def test_api_waits_for_a_healthy_database(compose):
    api, db = compose["services"]["api"], compose["services"]["db"]
    assert api["depends_on"] == {"db": {"condition": "service_healthy"}}
    test = db["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL" and test[1].startswith("/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa")
    assert " -No " in test[1] and " -b " in test[1]


def test_sql_server_image_and_data_volume(compose):
    db = compose["services"]["db"]
    assert db["image"] == "mcr.microsoft.com/mssql/server:2025-latest"
    assert db["environment"]["ACCEPT_EULA"] == "Y" and db["environment"]["MSSQL_PID"] == "Developer"
    assert db["volumes"] == ["mssql-data:/var/opt/mssql"] and "mssql-data" in compose["volumes"]


def test_api_env_maps_to_the_apps_configuration(compose):
    settings = json.loads((APP / "src/Contoso.Orders.Api/appsettings.json").read_text())
    for key in compose["services"]["api"]["environment"]:
        section, name = key.split("__")
        assert name in settings[section], key
    assert compose["services"]["api"]["environment"]["Database__Provider"] == "SqlServer"


def test_watch_rebuilds_on_source_changes(compose):
    assert compose["services"]["api"]["develop"]["watch"] == [{"action": "rebuild", "path": "./src"}]


def test_dotenv_is_ignored_by_git_and_the_example_has_no_value():
    assert ".env" in (APP / ".gitignore").read_text().splitlines()
    example = (APP / ".env.example").read_text()
    assert re.search(r"^MSSQL_SA_PASSWORD=$", example, re.M)


BAD = {
    "DC001": {"services": {"a": {"image": "x:1", "ports": ["8080:8080"]}}},
    "DC002": {"services": {"a": {"image": "x:1", "environment": {"CS": "Server=db;Password=hunter2"}}}},
    "DC003": {"services": {"a": {"image": "x:1", "environment": {"SA_PASSWORD": "${SA_PASSWORD}"}}}},
    "DC004": {"services": {"a": {"image": "x:1", "depends_on": {"b": {"condition": "service_healthy"}}},
                           "b": {"image": "y:1"}}},
    "DC005": {"services": {"a": {"image": "x:1", "volumes": ["data:/data"]}}},
    "DC006": {"services": {"a": {"image": "mcr.microsoft.com/mssql/server"}}},
    "DC007": {"services": {"a": {"image": "x:1", "healthcheck": {"test": ["CMD-SHELL", "sqlcmd -P $MSSQL_SA_PASSWORD"]}}}},
}


@pytest.mark.parametrize("rule", sorted(BAD))
def test_each_rule_fires_on_its_bad_example(rule):
    assert rule in {f.rule for f in cl.lint_compose(BAD[rule])}


def test_lint_cli_on_the_repo(capsys):
    assert cl.main(["all", str(APP)]) == 0
    assert "0 error(s), 0 warning(s)" in capsys.readouterr().out
