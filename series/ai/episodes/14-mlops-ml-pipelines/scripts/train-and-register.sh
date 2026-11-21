#!/usr/bin/env bash
# Train on Azure ML, and register the model ONLY if the pipeline (which includes the gate) completed.
# Needs: Azure CLI with the ml extension, already signed in; RG and WS set. Run from the episode folder.
#   python -m slabreach generate --out build/raw        # the data the pipeline reads (aml/pipeline.yml, inputs.raw_data)
#   RG=rg-mglab-ai-14 WS=<workspace> scripts/train-and-register.sh
set -euo pipefail
: "${RG:?set RG to the resource group}" "${WS:?set WS to the Azure ML workspace name}"
MODEL="${MODEL_NAME:-sla-breach}"
POLL="${POLL_SECONDS:-20}"
OUT="${OUT_DIR:-build/decision}"

# 1. the model in production is the source of truth: its test AUC is stored as a tag on the registered model
BASE="$(az ml model show --name "$MODEL" --label latest --query tags.test_auc -o tsv -g "$RG" -w "$WS" 2>/dev/null || true)"
BASE="${BASE:-0}"
[ "$BASE" = "None" ] && BASE=0
echo "production AUC: $BASE (0 = no model registered yet)"

# 2. submit the pipeline with that baseline
JOB="$(az ml job create -f aml/pipeline.yml --set "inputs.baseline_auc=$BASE" --query name -o tsv -g "$RG" -w "$WS")"
echo "submitted job: $JOB"

# 3. wait; anything but Completed means no registration (a gate that says no makes the evaluate step, and so the job, fail)
while true; do
  STATUS="$(az ml job show --name "$JOB" --query status -o tsv -g "$RG" -w "$WS")"
  echo "status: $STATUS"
  case "$STATUS" in
    Completed) break ;;
    Failed|Canceled|NotResponding) echo "job $JOB ended as $STATUS: nothing is registered"; exit 1 ;;
  esac
  sleep "$POLL"
done

# 4. read the gate's decision and register the model with the evidence attached
az ml job download --name "$JOB" --output-name decision --download-path "$OUT" -g "$RG" -w "$WS"
FILE="$(find "$OUT" -name decision.json | head -n 1)"
[ -n "$FILE" ] || { echo "decision.json not found under $OUT"; exit 1; }
python3 - "$FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["promote"] is True, "decision.json says do not promote"
PY
AUC="$(python3 -c 'import json,sys; print(round(json.load(open(sys.argv[1]))["metrics"]["auc"], 4))' "$FILE")"
VERSION="$(az ml model create --name "$MODEL" --type mlflow_model --path "azureml://jobs/$JOB/outputs/model" \
  --set "tags.test_auc=$AUC" "tags.pipeline_job=$JOB" --query version -o tsv -g "$RG" -w "$WS")"
echo "registered $MODEL version $VERSION (test AUC $AUC)"
echo "$VERSION" > "$OUT/model_version.txt"
