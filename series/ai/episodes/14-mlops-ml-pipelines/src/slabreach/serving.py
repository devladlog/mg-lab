"""What the endpoint does with a request, reproduced locally. Learn's score.py ("Deploy MLflow models to online endpoints") reads
the top-level `input_data` key and parses it with MLflow's `infer_and_parse_json_input`. MLflow 3 removed that name; the
equivalent is `infer_and_parse_data` on a `dataframe_split` dict. For a no-code deployment Azure ML's own server does this work,
so this is a local approximation of it, good enough to catch a wrong column name or a wrong type before deploying."""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import mlflow.pyfunc
from mlflow.pyfunc import scoring_server


def parse_input(input_data: dict, schema):
    if hasattr(scoring_server, "infer_and_parse_json_input"):               # MLflow 2.x, as in Learn's score.py
        return scoring_server.infer_and_parse_json_input(json.dumps(input_data), schema)
    return scoring_server.infer_and_parse_data({"dataframe_split": input_data}, schema)   # MLflow 3.x


def predict_request(model_dir: Path, request_file: Path):
    body = json.loads(Path(request_file).read_text())
    if "input_data" not in body:
        raise ValueError("Request must contain a top level key named 'input_data'")
    model = mlflow.pyfunc.load_model(str(model_dir))
    data = parse_input(body["input_data"], model.metadata.get_input_schema())
    out = StringIO()
    scoring_server.predictions_to_json(model.predict(data), out)
    return json.loads(out.getvalue())
