import json
import subprocess
import sys

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
import pytest

from conftest import ROOT
from slabreach import cli
from slabreach.schema import FEATURES
from slabreach.serving import predict_request


def test_the_baseline_run_is_promoted(trained):
    assert trained["code"] == 0
    d = json.loads((trained["dir"] / "decision" / "decision.json").read_text())
    assert d["promote"] is True and d["metrics"]["auc"] > 0.70
    assert d["metrics"]["p1_breaches"] > 10 and d["thresholds"]["min_auc"] == 0.70


def test_model_is_an_mlflow_model_with_a_signature_and_probability_output(trained):
    m = trained["dir"] / "model"
    assert (m / "MLmodel").exists() and (m / "conda.yaml").exists()
    model = mlflow.pyfunc.load_model(str(m))
    assert [c.name for c in model.metadata.get_input_schema().inputs] == FEATURES
    df = pd.DataFrame([["P1", "network", "email", 8.0, 4.0, 320.0]], columns=FEATURES)
    p = np.asarray(model.predict(df))
    assert p.shape == (1, 2) and abs(p.sum() - 1) < 1e-6                 # [P(no breach), P(breach)]


def test_the_model_learned_something_sensible(trained):
    model = mlflow.pyfunc.load_model(str(trained["dir"] / "model"))
    risky = pd.DataFrame([["P1", "network", "email", 8.0, 4.0, 900.0]], columns=FEATURES)
    safe = pd.DataFrame([["P4", "access", "phone", 11.0, 1.0, 60.0]], columns=FEATURES)
    assert np.asarray(model.predict(risky))[0, 1] > 0.6 > 0.3 > np.asarray(model.predict(safe))[0, 1]


def test_metrics_and_params_were_logged_to_mlflow(trained):
    c = mlflow.MlflowClient((trained["dir"] / "mlruns").as_uri())
    runs = c.search_runs([e.experiment_id for e in c.search_experiments()])
    r = runs[0]
    assert {"train_auc", "test_auc", "test_p1_recall", "promote"} <= set(r.data.metrics)
    assert r.data.params["seed"] == "7" and r.data.metrics["promote"] == 1.0


def test_training_is_reproducible(tmp_path, trained):
    t = trained["dir"]
    cli.main(["train", "--train", str(t / "train"), "--model-out", str(tmp_path / "m2")])
    from slabreach.evaluate import metrics_for
    assert metrics_for(tmp_path / "m2", t / "test")["auc"] == pytest.approx(json.loads((t / "decision" / "decision.json").read_text())["metrics"]["auc"])


def test_a_noisy_extract_is_rejected_by_the_gate_and_exit_code_is_3(tmp_path):
    cli.main(["generate", "--out", str(tmp_path / "raw"), "--scenario", "noisy", "--seed", "4"])
    cli.main(["prepare", "--raw", str(tmp_path / "raw"), "--train-out", str(tmp_path / "tr"), "--test-out", str(tmp_path / "te")])
    with mlflow.start_run():
        cli.main(["train", "--train", str(tmp_path / "tr"), "--model-out", str(tmp_path / "m")])
        code = cli.main(["evaluate", "--model", str(tmp_path / "m"), "--test", str(tmp_path / "te"), "--out", str(tmp_path / "ev"), "--baseline-auc", "0.78"])
    d = json.loads((tmp_path / "ev" / "decision.json").read_text())
    assert code == 3 and d["promote"] is False and any("production" in r for r in d["reasons"])


def test_sample_request_goes_through_the_same_parsing_as_the_endpoint(trained):
    out = predict_request(trained["dir"] / "model", ROOT / "aml" / "sample-request.json")
    preds = out["predictions"] if isinstance(out, dict) else out
    assert len(preds) == 2 and len(preds[0]) == 2
    assert preds[0][1] > preds[1][1]                                      # the P1 network ticket is riskier than the P4 one


def test_request_without_input_data_is_refused(trained, tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"inputs": {"columns": FEATURES, "data": []}}))
    with pytest.raises(ValueError, match="input_data"):
        predict_request(trained["dir"] / "model", f)


def test_the_cli_runs_as_a_module_the_way_the_components_call_it(tmp_path):
    r = subprocess.run([sys.executable, "-m", "slabreach", "generate", "--out", str(tmp_path), "--rows", "50"], cwd=ROOT / "src", capture_output=True, text=True)
    assert r.returncode == 0 and (tmp_path / "tickets.csv").exists()
