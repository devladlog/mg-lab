"""Plain-text tables for the terminal."""
from __future__ import annotations


def protocols(rows: list[dict], kinds=("logistic", "forest")) -> str:
    head = f"{'evaluation':<27}{'test rows':>10}{'shared people':>14}{'prevalence':>11}" + "".join(f"{k + ' AP':>14}{k + ' AUC':>14}" for k in kinds)
    lines = [head]
    for r in rows:
        lines.append(f"{r['protocol']:<27}{r['test']:>10,}{r['shared_requesters']:>14}{r['prevalence']:>11.1%}"
                     + "".join(f"{r[k]['avg_precision']:>14.3f}{r[k]['roc_auc']:>14.3f}" for k in kinds))
    lines.append("AP = average precision (a model with no skill scores the prevalence); AUC = ROC area (no skill = 0.5)")
    return "\n".join(lines)


def baseline(b: dict) -> str:
    lines = [f"{'model':<26}{'accuracy':>10}{'AUC':>8}{'AP':>8}{'Brier':>8}"]
    names = {"dummy": "always the prior (no skill)", "logistic": "logistic regression"}
    for k, s in b.items():
        lines.append(f"{names[k]:<26}{s['accuracy']:>10.3f}{s['roc_auc']:>8.3f}{s['avg_precision']:>8.3f}{s['brier']:>8.3f}")
    lines.append(f"prevalence of breaches in the test requesters: {next(iter(b.values()))['prevalence']:.1%}")
    return "\n".join(lines)


def depth(rows: list[dict]) -> str:
    lines = [f"{'max_depth':>10}{'train AP':>10}{'validation AP':>15}{'gap':>8}"]
    for r in rows:
        lines.append(f"{str(r['max_depth']):>10}{r['train']:>10.3f}{r['validation']:>15.3f}{r['train'] - r['validation']:>8.3f}")
    best = max(rows, key=lambda r: r["validation"])
    lines.append(f"best validation: max_depth={best['max_depth']}; a deeper tree only memorises the training tickets")
    return "\n".join(lines)


def training(res: dict, ok: bool, why: list[str]) -> str:
    c, t = res["confusion"], res["test"]
    lines = ["grouped 5-fold CV on the training rows (average precision):"]
    for r in res["ranking"]:
        lines.append(f"  {r['kind']:<9}{str(r['params']):<28}{r['cv_avg_precision']:.3f}")
    lines += [
        f"chosen: {res['chosen']['kind']} {res['chosen']['params']}",
        f"threshold {res['threshold']:.3f} (cost of a missed breach {res['cost_fn']:g}, of a false alarm {res['cost_fp']:g}; chosen on out-of-fold predictions)",
        f"test once: {res['rows']['test']:,} tickets from {res['rows']['test_requesters']} requesters never seen in training",
        f"  AUC {t['roc_auc']:.3f}   average precision {t['avg_precision']:.3f} (prevalence {t['prevalence']:.3f})   Brier {t['brier']:.3f}",
        f"  at the threshold: caught {c['tp']} of {c['tp'] + c['fn']} breaches (recall {c['recall']:.0%}), "
        f"{c['fp']} false alarms (precision {c['precision']:.0%})",
        f"  cost: model {res['cost_model']:.0f}   flag nothing {res['cost_reference']['flag_nothing']:.0f}   "
        f"flag everything {res['cost_reference']['flag_everything']:.0f}",
        "RESULT: " + ("ship candidate" if ok else "do not ship: " + "; ".join(why)),
    ]
    return "\n".join(lines)
