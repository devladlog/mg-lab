import json

import pytest

from fttriage import dataset, jobs
from fttriage.prompts import SHORT_SYSTEM


@pytest.fixture
def files(tmp_path, data):
    _, _, sp = data
    t, v = tmp_path / "training.jsonl", tmp_path / "validation.jsonl"
    dataset.write_jsonl(t, [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.train])
    dataset.write_jsonl(v, [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.validation])
    return t, v


def test_upload_sends_the_file_with_purpose_fine_tune_and_an_entra_token(stub, client, files):
    fid = jobs.upload(client, files[0])
    req = stub.last("POST", "/openai/v1/files")
    assert req["auth"] == "Bearer fake-entra-token"
    assert client.test_credential.scopes == ["https://ai.azure.com/.default"]
    assert b'name="purpose"' in req["body"] and b"fine-tune" in req["body"]
    assert b"\xef\xbb\xbf" in req["body"]                     # the BOM we wrote goes over the wire untouched
    assert fid.startswith("file-")
    assert any(r["method"] == "GET" and r["path"].endswith(f"/files/{fid}") for r in stub.requests)   # waited for processing


def test_submit_body_matches_learns_sft_example(stub, client):
    rec = jobs.submit(client, "gpt-4.1-mini-2025-04-14", "file-1", "file-2", training_type="Standard", suffix="hr-triage")
    body = json.loads(stub.last("POST", "/fine_tuning/jobs")["body"])
    assert body["model"] == "gpt-4.1-mini-2025-04-14"
    assert (body["training_file"], body["validation_file"], body["suffix"], body["seed"]) == ("file-1", "file-2", "hr-triage", 7)
    assert body["trainingType"] == "Standard"                 # top-level field, set through extra_body
    assert body["method"] == {"type": "supervised", "supervised": {"hyperparameters": {
        "batch_size": "auto", "learning_rate_multiplier": "auto", "n_epochs": "auto"}}}
    assert rec.job_id == "ftjob-1" and rec.status == "queued"


def test_explicit_hyperparameters_and_training_type_validation(stub, client):
    jobs.submit(client, "m", "f1", "f2", n_epochs=2, learning_rate_multiplier=0.5, training_type="GlobalStandard")
    hp = json.loads(stub.last("POST", "/fine_tuning/jobs")["body"])["method"]["supervised"]["hyperparameters"]
    assert hp["n_epochs"] == 2 and hp["learning_rate_multiplier"] == 0.5
    with pytest.raises(ValueError):
        jobs.submit(client, "m", "f1", "f2", training_type="Developer")      # API value not documented: refused


def test_wait_follows_the_job_to_the_fine_tuned_model(stub, client):
    rec = jobs.submit(client, "gpt-4.1-mini-2025-04-14", "f1", "f2")
    seen = []
    done = jobs.wait(client, rec, poll_seconds=0, on_event=seen.append, sleep=lambda s: None)
    assert done.status == "succeeded" and done.fine_tuned_model == stub.fine_tuned_model
    assert done.result_files == ["file-results"]
    assert "[queued] Job enqueued" in seen[0] or any("Job enqueued" in s for s in seen)
    assert stub.job_polls == 3                                 # queued, running, succeeded: no resubmission
    assert len([r for r in stub.requests if r["method"] == "POST" and r["path"].endswith("/fine_tuning/jobs")]) == 1


def test_a_failed_job_raises_with_the_service_message(stub, client):
    stub.job_states = ["running", "failed"]
    rec = jobs.submit(client, "m", "f1", "f2")
    with pytest.raises(RuntimeError, match="line 3 is not valid"):
        jobs.wait(client, rec, poll_seconds=0, sleep=lambda s: None)


def test_wait_times_out_but_says_the_job_keeps_running(stub, client):
    stub.job_states = ["queued"]
    rec = jobs.submit(client, "m", "f1", "f2")
    with pytest.raises(TimeoutError, match="keeps running"):
        jobs.wait(client, rec, poll_seconds=0, timeout_seconds=-1, sleep=lambda s: None)


def test_metrics_download_and_parse(stub, client):
    rec = jobs.submit(client, "m", "f1", "f2")
    rec = jobs.wait(client, rec, poll_seconds=0, sleep=lambda s: None)
    rows = jobs.fetch_metrics(client, rec)
    assert [r["step"] for r in rows] == [1, 10, 20]
    assert rows[0]["full_valid_loss"] is None and rows[-1]["full_valid_mean_token_accuracy"] == 0.85
    assert jobs.overfit_signal(rows) is None


def test_overfitting_signal_when_validation_loss_rises():
    rows = jobs.read_metrics("step,train_loss,full_valid_loss\n1,1.0,0.50\n10,0.4,0.55\n20,0.05,0.80\n")
    msg = jobs.overfit_signal(rows)
    assert msg and "possible overfitting" in msg and "0.050" in msg and "0.800" in msg


def test_job_record_roundtrip(tmp_path):
    rec = jobs.JobRecord("ftjob-1", "gpt-4.1-mini-2025-04-14", "Standard", "f1", "f2", "succeeded", "ft:model")
    rec.save(tmp_path / "x" / "job.json")
    assert jobs.JobRecord.load(tmp_path / "x" / "job.json") == rec
