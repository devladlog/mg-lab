import json
import pathlib
import re
import shutil
import subprocess

import pytest

from analytics.__main__ import main

ROOT = pathlib.Path(__file__).resolve().parents[1]
BICEP = (ROOT / "infra" / "main.bicep").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("bicep") is None, reason="bicep CLI not installed")
def test_bicep_builds_and_lints_clean():
    built = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    assert "warning" not in built.stderr.lower()
    lint = subprocess.run(["bicep", "lint", str(ROOT / "infra" / "main.bicep")], capture_output=True, text=True)
    assert lint.returncode == 0 and "warning" not in (lint.stdout + lint.stderr).lower()
    arm = json.loads(built.stdout)
    types = {r["type"] for r in (arm["resources"].values() if isinstance(arm["resources"], dict) else arm["resources"])}
    assert {"Microsoft.Synapse/workspaces", "Microsoft.DataFactory/factories/pipelines", "Microsoft.Storage/storageAccounts"} <= types


def test_no_secrets_and_entra_only_everywhere():
    assert re.search(r"azureADOnlyAuthentication: true", BICEP)
    assert "authenticationType: 'SystemAssignedManagedIdentity'" in BICEP
    assert "allowSharedKey bool = false" in BICEP
    assert not re.search(r"(accountKey|connectionString|password)\s*:\s*'[^']+'", BICEP, re.I)
    assert "param synapseSqlPassword string = newGuid()" in BICEP, "the unused Synapse admin password must be random, not typed"


def test_source_database_uses_the_free_offer_and_pauses_instead_of_billing():
    assert "useFreeLimit: true" in BICEP and "freeLimitExhaustionBehavior: 'AutoPause'" in BICEP


def test_factory_identity_gets_contributor_on_the_lake_and_nothing_wider():
    assert "roleBlobContributor" in BICEP and "scope: storage" in BICEP
    for wide in ("8e3af657-a8ff-443c-a75c-2fe8c4bcb635", "b24988ac-6180-42a0-ab88-20f7382dd24c"):   # Owner, Contributor
        assert wide not in BICEP


def test_pipeline_activities_retry_because_the_free_database_pauses():
    pipe = json.loads((ROOT / "adf" / "pipeline-incremental.json").read_text())
    for a in pipe["activities"]:
        if a["type"] in ("Lookup", "SqlServerStoredProcedure"):
            assert a["policy"]["retry"] >= 3 and a["policy"]["retryIntervalInSeconds"] >= 60


def test_cli_seed_sql_writes_both_phases(tmp_path):
    p1, p2 = tmp_path / "p1.sql", tmp_path / "p2.sql"
    assert main(["seed-sql", "--phase", "1", "--out", str(p1)]) == 0
    assert main(["seed-sql", "--phase", "2", "--out", str(p2)]) == 0
    assert p1.read_text().count("MERGE dbo.PurchaseRequests") >= 5
    assert p1.stat().st_size > p2.stat().st_size > 1000


def test_cli_seed_phase_three_is_the_four_bad_rows(tmp_path):
    out = tmp_path / "p3.sql"
    assert main(["seed-sql", "--phase", "3", "--out", str(out)]) == 0
    text = out.read_text()
    assert text.count("(9001,") == 1 and "(9004," in text and "-50.00" in text and "N'ZZZ'" in text


def test_cli_train_export_drift_roundtrip(tmp_path, capsys):
    assert main(["make-bronze", "--out", str(tmp_path), "--defects"]) == 0
    assert main(["train", "--lake", str(tmp_path), "--model", str(tmp_path / "m.json")]) == 0
    assert main(["export-sql", "--model", str(tmp_path / "m.json"), "--out", str(tmp_path / "s.sql")]) == 0
    assert main(["drift", "--lake", str(tmp_path), "--model", str(tmp_path / "m.json")]) == 0
    out = capsys.readouterr().out
    assert "PSI(amount) =" in out and "sla-breach-lr-" in out
    assert "CREATE OR ALTER VIEW gold.RequestRiskScore" in (tmp_path / "s.sql").read_text()
