from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SAMPLES = SRC / "samples"
CLEAN = SAMPLES / "purchase-requests-eventlog.csv"
RAW = SAMPLES / "purchase-requests-eventlog-raw.csv"
