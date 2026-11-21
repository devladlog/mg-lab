"""
Pipeline contract: checks an Azure Pipelines YAML file (and its stage templates) for the rules this team
agreed on, before Azure DevOps ever sees it. It is not a full YAML-pipeline compiler: it expands
`template:` references and `${{ parameters.x }}` substitutions (the only template expressions we allow),
then checks the resulting stage graph.

Rules
  T1  every template file exists; passed parameters are declared; required ones are passed; basic types match
  T2  only ${{ parameters.x }} expressions are used (no ${{ if }} / ${{ each }}), so the expansion here is exact
  S1  stage names are unique and every dependsOn points to an earlier stage
  S2  deploy stages (deployment jobs) run only for refs/heads/main
  S3  a stage that deploys to an approval environment depends on a plan stage for the same service connection
  J1  deployment jobs target an environment and check out the repo if they use repo files
  K1  azureSubscription is known at compile time (no $(var) or $[ ] runtime expressions)
  K2  every task is pinned to a major version (Task@N)
  R1  no YAML `pr:` trigger other than `none` (Azure Repos Git uses a Build validation branch policy instead)
  X1  no secret-looking values in any of the files
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

PARAM_EXPR = re.compile(r"\$\{\{\s*parameters\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
ANY_EXPR = re.compile(r"\$\{\{(.*?)\}\}")
SECRET_PATTERNS = [
    re.compile(r"AccountKey=[A-Za-z0-9+/=]{20,}"),
    re.compile(r"[?&]sig=[A-Za-z0-9%+/=]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)client_?secret\s*[:=]\s*['\"]?[A-Za-z0-9~._-]{20,}"),
]
TYPES = {"string": str, "boolean": bool, "number": (int, float), "object": (list, dict, str, int, float, bool)}


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    files: list[pathlib.Path] = field(default_factory=list)

    def add(self, rule: str, msg: str) -> None:
        self.problems.append(f"{rule} {msg}")

    def graph(self) -> list[str]:
        lines = []
        for s in self.stages:
            deps = s.get("dependsOn") or []
            deps = [deps] if isinstance(deps, str) else deps
            envs = [j.get("environment") for j in s.get("jobs", []) if "deployment" in j]
            kind = f"deploy -> {envs[0]}" if envs else ("plan" if is_plan(s) else "jobs")
            lines.append(f"{s['stage']:<10} needs [{', '.join(deps)}]  ({kind})")
        return lines


def substitute(node: Any, values: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {substitute(k, values): substitute(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [substitute(v, values) for v in node]
    if isinstance(node, str):
        whole = PARAM_EXPR.fullmatch(node.strip())
        if whole and whole.group(1) in values:
            return values[whole.group(1)]
        return PARAM_EXPR.sub(lambda m: _render(values.get(m.group(1), m.group(0))), node)
    return node


def _render(v: Any) -> str:
    return ("True" if v else "False") if isinstance(v, bool) else str(v)


def declared(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in (doc.get("parameters") or [])}


def check_expressions(path: pathlib.Path, text: str, report: Report) -> None:
    for m in ANY_EXPR.finditer(text):
        if not PARAM_EXPR.fullmatch(m.group(0)):
            report.add("T2", f"{path.name}: unsupported template expression {m.group(0)!r}")
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            report.add("X1", f"{path.name}: secret-looking value matches {pat.pattern!r}")


def bind(template: pathlib.Path, doc: dict[str, Any], passed: dict[str, Any], report: Report) -> dict[str, Any]:
    decl = declared(doc)
    values = {}
    for name in passed:
        if name not in decl:
            report.add("T1", f"{template.name}: parameter {name!r} is passed but not declared")
    for name, spec in decl.items():
        if name in passed:
            value = passed[name]
        elif "default" in spec:
            value = spec["default"]
        else:
            report.add("T1", f"{template.name}: required parameter {name!r} is not passed")
            continue
        expected = TYPES.get(spec.get("type", "string"))
        unresolved = isinstance(value, str) and ANY_EXPR.search(value)
        if expected and not unresolved and not isinstance(value, expected):
            report.add("T1", f"{template.name}: parameter {name!r} should be {spec.get('type')}, got {value!r}")
        values[name] = value
    return values


def expand(pipeline: pathlib.Path, report: Report) -> dict[str, Any]:
    text = pipeline.read_text(encoding="utf-8")
    report.files.append(pipeline)
    check_expressions(pipeline, text, report)
    root = yaml.safe_load(text)
    runtime = {n: p.get("default") for n, p in declared(root).items()}
    stages = []
    for item in substitute(root.get("stages", []), runtime):
        if "template" not in item:
            stages.append(item)
            continue
        tpath = (pipeline.parent / item["template"]).resolve()
        if not tpath.is_file():
            report.add("T1", f"template not found: {item['template']}")
            continue
        ttext = tpath.read_text(encoding="utf-8")
        if tpath not in report.files:
            report.files.append(tpath)
            check_expressions(tpath, ttext, report)
        tdoc = yaml.safe_load(ttext)
        values = bind(tpath, tdoc, item.get("parameters") or {}, report)
        stages.extend(substitute(tdoc.get("stages", []), values))
    root["stages"] = stages
    return root


def steps_of(job: dict[str, Any]) -> list[dict[str, Any]]:
    if "deployment" in job:
        strategy = job.get("strategy", {}).get("runOnce", {})
        return [s for hook in strategy.values() for s in (hook or {}).get("steps", [])]
    return job.get("steps", [])


def connections(stage: dict[str, Any]) -> set[str]:
    return {str(s["inputs"]["azureSubscription"]) for j in stage.get("jobs", []) for s in steps_of(j)
            if isinstance(s.get("inputs"), dict) and "azureSubscription" in s["inputs"]}


def is_plan(stage: dict[str, Any]) -> bool:
    jobs = stage.get("jobs", [])
    return bool(jobs) and all("deployment" not in j for j in jobs) and bool(connections(stage))


def check(pipeline: pathlib.Path, approval_envs: set[str]) -> Report:
    report = Report()
    root = expand(pipeline, report)
    report.stages = root["stages"]

    pr = root.get("pr", None)
    if pr is not None and pr != "none":
        report.add("R1", "YAML pr triggers are ignored for Azure Repos Git; use a Build validation branch policy")

    seen: dict[str, dict[str, Any]] = {}
    for stage in report.stages:
        name = stage.get("stage")
        if name in seen:
            report.add("S1", f"duplicate stage name {name!r}")
        deps = stage.get("dependsOn") or []
        deps = [deps] if isinstance(deps, str) else deps
        for d in deps:
            if d not in seen:
                report.add("S1", f"stage {name!r} depends on {d!r}, which is not an earlier stage")

        deploys = [j for j in stage.get("jobs", []) if "deployment" in j]
        if (deploys or is_plan(stage)) and "refs/heads/main" not in str(stage.get("condition", "")):
            report.add("S2", f"stage {name!r} touches Azure but isn't limited to refs/heads/main")

        for job in stage.get("jobs", []):
            steps = steps_of(job)
            if "deployment" in job:
                if not job.get("environment"):
                    report.add("J1", f"deployment job in {name!r} has no environment")
                uses_repo = "$(pipelineDir)" in str(steps) or "$(workloadDir)" in str(steps)
                if uses_repo and not any(s.get("checkout") == "self" for s in steps):
                    report.add("J1", f"deployment job in {name!r} uses repo files but has no 'checkout: self'")
            for s in steps:
                task = s.get("task")
                if task and not re.fullmatch(r"[A-Za-z0-9._-]+@\d+", task):
                    report.add("K2", f"task {task!r} in {name!r} isn't pinned to a major version")
                sub = (s.get("inputs") or {}).get("azureSubscription")
                if sub is not None and re.search(r"\$\(|\$\[|\$\{\{", str(sub)):
                    report.add("K1", f"azureSubscription {sub!r} in {name!r} is not known at compile time")

        for job in deploys:
            if job.get("environment") in approval_envs:
                plans = [seen[d] for d in deps if d in seen and is_plan(seen[d])]
                if not any(connections(p) & connections(stage) for p in plans):
                    report.add("S3", f"stage {name!r} deploys to approval environment {job['environment']!r} "
                                     "without depending on a plan stage for the same service connection")
        seen[name] = stage
    return report
