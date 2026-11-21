"""Nothing here calls Azure. The data, the three pipeline steps, the MLflow model and the request format run for real on this
machine. What is NOT tested here: the cloud itself (a job on a cluster, the registry, an endpoint). The shell scripts are run against
a stand-in `az` that records its arguments, to test their logic (order of calls, no registration after a failed job)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")        # MLflow 3 refuses the file store otherwise; Azure ML sets its own tracking URI
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


@pytest.fixture(autouse=True)
def tracking(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", (tmp_path / "mlruns").as_uri())
    import mlflow
    mlflow.set_tracking_uri((tmp_path / "mlruns").as_uri())
    yield
    if mlflow.active_run():
        mlflow.end_run()


@pytest.fixture(scope="session")
def trained(tmp_path_factory):
    """One real run of generate, prepare, train, evaluate on the baseline data, shared by the tests that need a model."""
    import mlflow
    from slabreach import cli
    t = tmp_path_factory.mktemp("run")
    mlflow.set_tracking_uri((t / "mlruns").as_uri())
    assert cli.main(["generate", "--out", str(t / "raw"), "--seed", "1"]) == 0
    assert cli.main(["prepare", "--raw", str(t / "raw"), "--train-out", str(t / "train"), "--test-out", str(t / "test")]) == 0
    with mlflow.start_run():
        assert cli.main(["train", "--train", str(t / "train"), "--model-out", str(t / "model")]) == 0
        code = cli.main(["evaluate", "--model", str(t / "model"), "--test", str(t / "test"), "--out", str(t / "decision")])
    return {"dir": t, "code": code}
