#!/usr/bin/env python3
"""ai-readiness: check the data and the model BEFORE you drop an AI visual on the canvas.

The AI visuals fail quietly or with a generic message ("no influencers found", "not enough data"). The
limits below come from Microsoft Learn; this tool turns them into a checklist you can run on the CSV.

Rules
  AI001 error    outcome state has fewer than 100 observations          (key influencers: "at least 100 observations for the selected state")
  AI002 error    comparison state has fewer than 10 observations        (key influencers: "at least 10 observations for the states you use for comparison")
  AI003 warning  outcome has more than 10 unique values                 (key influencers warning: quality drops with many categories)
  AI004 warning  an Explain by category has fewer than 10 observations  (key influencers: "too many categories with few observations")
  AI005 info     more than 10,000 rows: the visual analyses a sample of 10,000 data points
  AI006 error    the outcome is also in Explain by                      (key influencers: remove it from Explain by)
  AI007 error    model has discourageImplicitMeasures and the outcome is categorical
  AI008 error    fewer than 4 data points for anomaly detection
  AI009 error    the series has two points on the same date (a line chart on a date axis needs one value per date)

Usage:
    python ai_readiness.py --star <star folder> --model <SemanticModel/definition> \
        [--outcome "Survey Rating"] [--target Low] [--explain "Channel,Contains Bike"]
Exit code 1 when any error is reported.
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

MIN_TARGET = 100        # Learn: at least 100 observations for the selected state
MIN_COMPARISON = 10     # Learn: at least 10 observations for the comparison states
MAX_UNIQUE = 10         # Learn: warning above 10 unique values in the analysed metric
SAMPLE_CAP = 10_000     # Learn: the visual runs on a sample of 10,000 data points
MIN_POINTS = 4          # Learn (anomaly detection): at least 4 data points

# CSV header (no spaces) for each field name as the report shows it
COLUMN = {"Order Number": "OrderNumber", "Order Date": "OrderDate", "Channel": "Channel",
          "Store Country": "StoreCountry", "Customer Country": "CustomerCountry",
          "Contains Bike": "ContainsBike", "Lines": "Lines", "Units": "Units", "Order Value": "OrderValue",
          "Order Size": "OrderSize", "Ship Days": "ShipDays", "Delivery": "Delivery", "Survey Rating": "SurveyRating"}


def finding(rule, severity, message):
    return {"rule": rule, "severity": severity, "message": message}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def discourages_implicit_measures(model_dir):
    text = (Path(model_dir) / "model.tmdl").read_text(encoding="utf-8")
    return re.search(r"^\s*discourageImplicitMeasures\s*(?::\s*true)?\s*$", text, flags=re.M) is not None


def check_key_influencers(rows, outcome, target, explain, model_dir=None):
    """Findings for a key influencers visual: Analyze = outcome, Explain by = explain, state = target."""
    out = []
    col = COLUMN[outcome]
    counts = Counter(r[col] for r in rows)
    n_target = counts.get(target, 0)
    if n_target < MIN_TARGET:
        out.append(finding("AI001", "error", f"{outcome} = {target} has {n_target} observations; the visual needs at least {MIN_TARGET}."))
    n_other = len(rows) - n_target
    if n_other < MIN_COMPARISON:
        out.append(finding("AI002", "error", f"only {n_other} observations are not {target}; the visual needs at least {MIN_COMPARISON} to compare."))
    if len(counts) > MAX_UNIQUE:
        out.append(finding("AI003", "warning", f"{outcome} has {len(counts)} unique values; above {MAX_UNIQUE} the quality drops. Group them or use Continuous analysis."))
    for field in explain:
        if field == outcome:
            out.append(finding("AI006", "error", f"{outcome} is in Explain by and in Analyze; remove it from Explain by."))
            continue
        thin = sorted(v for v, n in Counter(r[COLUMN[field]] for r in rows).items() if n < MIN_COMPARISON)
        if thin:
            out.append(finding("AI004", "warning", f"{field} has {len(thin)} categories with fewer than {MIN_COMPARISON} observations: {', '.join(thin[:5])}."))
    if len(rows) > SAMPLE_CAP:
        out.append(finding("AI005", "info", f"{len(rows)} rows; the visual analyses a sample of {SAMPLE_CAP} data points, so counts in the visual can differ from the table."))
    if model_dir is not None and discourages_implicit_measures(model_dir):
        out.append(finding("AI007", "error", "the model sets discourageImplicitMeasures; key influencers does not support a categorical metric in that case."))
    return out


def check_anomaly_series(points):
    """points: list of (date_string, value) as they would sit on the line chart axis."""
    out = []
    if len(points) < MIN_POINTS:
        out.append(finding("AI008", "error", f"{len(points)} data points; anomaly detection needs at least {MIN_POINTS}."))
    dup = sorted(d for d, n in Counter(d for d, _ in points).items() if n > 1)
    if dup:
        out.append(finding("AI009", "error", f"{len(dup)} dates appear more than once (first: {dup[0]}); aggregate to one value per date."))
    return out


def daily_sales(star_dir):
    """(date, sum of quantity x unit price) per order date, from fact_sales.csv."""
    totals = Counter()
    for r in read_csv(Path(star_dir) / "fact_sales.csv"):
        totals[r["OrderDate"]] += float(r["Quantity"]) * float(r["UnitPrice"])
    return sorted((d, round(v, 2)) for d, v in totals.items())


def render(findings):
    order = {"error": 0, "warning": 1, "info": 2}
    return "\n".join(f"{f['rule']} {f['severity']:<7} {f['message']}" for f in sorted(findings, key=lambda f: (order[f["severity"]], f["rule"])))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--outcome", default="Survey Rating")
    ap.add_argument("--target", default="Low")
    ap.add_argument("--explain", default="Channel,Store Country,Customer Country,Contains Bike,Lines,Delivery")
    a = ap.parse_args(argv)
    rows = read_csv(Path(a.star) / "order_profile.csv")
    findings = check_key_influencers(rows, a.outcome, a.target, [x.strip() for x in a.explain.split(",")], a.model)
    findings += check_anomaly_series(daily_sales(a.star))
    print(render(findings) or "no findings")
    return 1 if any(f["severity"] == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
