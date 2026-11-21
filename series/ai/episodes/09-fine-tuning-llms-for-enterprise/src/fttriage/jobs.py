"""Upload, train, watch: supervised fine-tuning on the Azure OpenAI v1 endpoint with the plain OpenAI SDK."""
from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import openai

TRAINING_TYPES = ("Standard", "GlobalStandard")   # the two API values Learn documents; Standard keeps data in region
TERMINAL = {"succeeded", "failed", "cancelled"}


def make_client(endpoint: str, credential=None) -> openai.OpenAI:
    """Entra ID token provider, no key. Needs the Cognitive Services OpenAI Contributor role to fine-tune."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(credential or DefaultAzureCredential(), "https://ai.azure.com/.default")
    return openai.OpenAI(base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=provider)


@dataclass
class JobRecord:
    job_id: str
    base_model: str
    training_type: str
    training_file: str
    validation_file: str
    status: str = "queued"
    fine_tuned_model: str | None = None
    result_files: list[str] = field(default_factory=list)
    error: str | None = None

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "JobRecord":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def upload(client: openai.OpenAI, path: str | Path) -> str:
    with open(path, "rb") as f:
        file = client.files.create(file=f, purpose="fine-tune")
    client.files.wait_for_processing(file.id)
    return file.id


def submit(client: openai.OpenAI, model: str, training_file: str, validation_file: str, *,
           training_type: str = "Standard", suffix: str = "hr-triage", n_epochs="auto", batch_size="auto",
           learning_rate_multiplier="auto", seed: int | None = 7) -> JobRecord:
    if training_type not in TRAINING_TYPES:
        raise ValueError(f"training_type must be one of {TRAINING_TYPES}")
    job = client.fine_tuning.jobs.create(
        model=model, training_file=training_file, validation_file=validation_file, suffix=suffix, seed=seed,
        method={"type": "supervised",
                "supervised": {"hyperparameters": {"batch_size": batch_size,
                                                    "learning_rate_multiplier": learning_rate_multiplier,
                                                    "n_epochs": n_epochs}}},
        extra_body={"trainingType": training_type},
    )
    return JobRecord(job.id, model, training_type, training_file, validation_file, job.status)


def wait(client: openai.OpenAI, rec: JobRecord, *, poll_seconds: float = 30, timeout_seconds: float = 6 * 3600,
         on_event=print, sleep=time.sleep) -> JobRecord:
    """Poll until the job is finished. A queued job is normal (don't resubmit); failure raises with the error."""
    deadline = time.monotonic() + timeout_seconds
    seen: set[str] = set()
    while True:
        job = client.fine_tuning.jobs.retrieve(rec.job_id)
        for ev in reversed(client.fine_tuning.jobs.list_events(rec.job_id).data):
            if ev.id not in seen:
                seen.add(ev.id)
                on_event(f"[{job.status}] {ev.message}")
        rec.status = job.status
        if job.status in TERMINAL:
            rec.fine_tuned_model = job.fine_tuned_model
            rec.result_files = list(job.result_files or [])
            rec.error = getattr(getattr(job, "error", None), "message", None)
            if job.status != "succeeded":
                raise RuntimeError(f"fine-tuning job {rec.job_id} {job.status}: {rec.error or 'see job events'}")
            return rec
        if time.monotonic() > deadline:
            raise TimeoutError(f"job {rec.job_id} still {job.status} after {timeout_seconds:.0f}s; it keeps running")
        sleep(poll_seconds)


def read_metrics(csv_text: str) -> list[dict]:
    """The job's results.csv: step, train_loss, train_mean_token_accuracy, full_valid_loss, ... Empty cells become None."""
    rows = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        rows.append({k: (float(v) if v not in ("", None) else None) for k, v in r.items()})
    return rows


def fetch_metrics(client: openai.OpenAI, rec: JobRecord) -> list[dict]:
    if not rec.result_files:
        return []
    return read_metrics(client.files.content(rec.result_files[0]).read().decode("utf-8"))


def overfit_signal(rows: list[dict]) -> str | None:
    """Learn: training loss falling while validation loss rises means inspect the failing validation examples
    (and try fewer epochs or a smaller learning rate multiplier). Compares the first and last full-validation points."""
    train = [r["train_loss"] for r in rows if r.get("train_loss") is not None]
    valid = [r["full_valid_loss"] for r in rows if r.get("full_valid_loss") is not None]
    if len(train) < 2 or len(valid) < 2:
        return None
    if train[-1] < train[0] and valid[-1] > valid[0]:
        return (f"training loss fell ({train[0]:.3f} -> {train[-1]:.3f}) while validation loss rose "
                f"({valid[0]:.3f} -> {valid[-1]:.3f}): possible overfitting")
    return None
