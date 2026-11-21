"""A small linter for the two Azure Pipelines files, written from Learn's Build Tools rules.

It is not a YAML schema validator for Azure Pipelines (that needs the service). It expands
`${{ parameters.x }}` and step templates, then checks what we can know offline: task ids and their inputs
against Learn's task reference (tests/fixtures/build-tools-tasks.json), step order, stage wiring,
service connections, and that no literal identifiers are in the file.
"""
import json
import re
from pathlib import Path

import yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TASKS = json.loads((FIXTURES / "build-tools-tasks.json").read_text())["tasks"]
INSTALLER = "microsoft-IsvExpTools.PowerPlatform-BuildTools.tool-installer.PowerPlatformToolInstaller@2"
BUILD_TOOLS_PREFIX = "microsoft-IsvExpTools.PowerPlatform-BuildTools."
SOLUTION_CHECKER_RULESET = "0ad12346-e108-40b8-a956-9a8f95ea18c9"  # Learn: Power Platform Checker task
SCRIPTS_USING_PAC = {"Set-SolutionVersion.ps1", "Invoke-SolutionPack.ps1"}
CONNECTIONS = {"mglab-dev", "mglab-test", "mglab-prod"}

PARAM = re.compile(r"\$\{\{\s*parameters\.(\w+)\s*\}\}")


def fill(text, values):
    return PARAM.sub(lambda m: str(values[m.group(1)]).lower() if isinstance(values[m.group(1)], bool) else str(values[m.group(1)]), text)


def load(path, params=None):
    text = Path(path).read_text()
    return yaml.safe_load(fill(text, params or {}))


def defaults(doc):
    return {p["name"]: p.get("default") for p in doc.get("parameters", [])}


def expand_steps(steps, base):
    """Replace `- template: x` steps by the steps of that file, with its parameters filled in."""
    out = []
    for step in steps:
        if "template" in step:
            tpl = load(base / step["template"], step.get("parameters", {}))
            out.extend(expand_steps(tpl["steps"], base))
        else:
            out.append(step)
    return out


def jobs_of(doc, base):
    """[(stage name or None, job dict with expanded 'steps')]"""
    result = []
    stages = doc.get("stages")
    if stages is None:
        job = {"job": "(single)", "steps": expand_steps(doc["steps"], base)}
        return [(None, job)]
    for stage in stages:
        for job in stage["jobs"]:
            job = dict(job)
            steps = job.get("steps") or job["strategy"]["runOnce"]["deploy"]["steps"]
            job["steps"] = expand_steps(steps, base)
            result.append((stage["stage"], job))
    return result


def script_of(step):
    return step.get("pwsh") or step.get("bash") or step.get("script") or ""


def lint(pipeline_path, scripts_dir):
    """Returns a list of problem strings; empty means the file passes."""
    pipeline_path = Path(pipeline_path)
    base = pipeline_path.parent
    raw = pipeline_path.read_text()
    probs = []
    doc = load(pipeline_path, defaults(yaml.safe_load(raw)))
    jobs = jobs_of(doc, base)

    for stage, job in jobs:
        where = f"{stage or 'pipeline'}/{job.get('job') or job.get('deployment')}"
        bt_seen = False
        installer_seen = False
        for step in job["steps"]:
            task = step.get("task")
            if task:
                if task.startswith(BUILD_TOOLS_PREFIX):
                    if task not in TASKS:
                        probs.append(f"{where}: unknown Build Tools task {task}")
                        continue
                    for key in step.get("inputs", {}):
                        if key not in TASKS[task]["inputs"]:
                            probs.append(f"{where}: {task.split('.')[-1]} has no input '{key}' on Learn")
                    if task == INSTALLER:
                        installer_seen = True
                    elif not installer_seen:
                        probs.append(f"{where}: {task.split('.')[-1]} runs before the Power Platform Tool Installer")
                    bt_seen = True
            else:
                text = script_of(step)
                for name in re.findall(r"scripts/([\w.-]+\.ps1)", text):
                    if not (Path(scripts_dir) / name).exists():
                        probs.append(f"{where}: script {name} does not exist")
                    if name in SCRIPTS_USING_PAC and not installer_seen:
                        probs.append(f"{where}: {name} needs pac but runs before the Tool Installer")

    # literals that must never be in a pipeline file
    for m in re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", raw):
        if m != SOLUTION_CHECKER_RULESET:
            probs.append(f"literal GUID {m}")
    if re.search(r"\.crm\d*\.dynamics\.com|onmicrosoft\.com", raw):
        probs.append("literal environment URL or tenant name")

    # service connections
    for stage, job in jobs:
        for step in job["steps"]:
            conn = step.get("inputs", {}).get("PowerPlatformSPN") if step.get("task") else None
            if conn is not None and conn not in CONNECTIONS:
                probs.append(f"{stage}: service connection '{conn}' is not one of {sorted(CONNECTIONS)}")
    return probs


def lint_release(pipeline_path, scripts_dir):
    """Rules that only make sense for build-and-release.yml."""
    pipeline_path = Path(pipeline_path)
    base = pipeline_path.parent
    probs = lint(pipeline_path, scripts_dir)
    doc = load(pipeline_path, defaults(yaml.safe_load(pipeline_path.read_text())))
    stages = {s["stage"]: s for s in doc["stages"]}
    jobs = {(st, j.get("job") or j.get("deployment")): j for st, j in jobs_of(doc, base)}

    if set(stages) != {"Build", "Test", "Prod"}:
        probs.append(f"stages are {sorted(stages)}, expected Build, Test, Prod")
        return probs
    if stages["Test"].get("dependsOn") != "Build":
        probs.append("Test must depend on Build")
    if stages["Prod"].get("dependsOn") != "Test":
        probs.append("Prod must depend on Test")
    for name in ("Test", "Prod"):
        cond = stages[name].get("condition", "")
        if "PullRequest" not in cond or "succeeded()" not in cond:
            probs.append(f"{name} must run only after success and never for a pull request")
        job = next(j for (st, _), j in jobs.items() if st == name)
        if "deployment" not in job:
            probs.append(f"{name} must be a deployment job (environments carry the approvals)")
        if job.get("environment") != f"equipmentdesk-{name.lower()}":
            probs.append(f"{name} job uses environment {job.get('environment')!r}")
        groups = [v["group"] for v in stages[name].get("variables", []) if isinstance(v, dict) and "group" in v]
        if groups != [f"equipmentdesk-{name.lower()}"]:
            probs.append(f"{name} uses variable groups {groups}")
        conns = {s["inputs"]["PowerPlatformSPN"] for s in job["steps"] if s.get("task") and "PowerPlatformSPN" in s.get("inputs", {})}
        if conns != {f"mglab-{name.lower()}"}:
            probs.append(f"{name} uses service connections {sorted(conns)}")
        imports = [s for s in job["steps"] if s.get("task", "").endswith("PowerPlatformImportSolution@2")]
        if len(imports) != 1:
            probs.append(f"{name} must import exactly once")
        for s in imports:
            i = s["inputs"]
            if i.get("SolutionInputFile") != "$(managedZip)":
                probs.append(f"{name} imports {i.get('SolutionInputFile')!r}; only the managed zip may be deployed")
            if i.get("UseDeploymentSettingsFile") is not True:
                probs.append(f"{name} does not use a deployment settings file")
            if i.get("DeploymentSettingsFile") != f"$(Agent.TempDirectory)/{name.lower()}.settings.json":
                probs.append(f"{name} reads settings from {i.get('DeploymentSettingsFile')!r}, not the file the resolve step writes")
            if i.get("OverwriteUnmanagedCustomizations") is True:
                probs.append(f"{name} overwrites unmanaged customizations")
            if i.get("AsyncOperation") is not True:
                probs.append(f"{name} import is not asynchronous")
        resolve = [s for s in job["steps"] if "Resolve-DeploymentSettings.ps1" in script_of(s)]
        if len(resolve) != 1 or f"settings/{name.lower()}.settings.json" not in script_of(resolve[0]):
            probs.append(f"{name} must resolve settings/{name.lower()}.settings.json exactly once")
        upgrades = [s for s in job["steps"] if s.get("task", "").endswith("PowerPlatformApplySolutionUpgrade@2")]
        if len(upgrades) != 1 or "succeeded()" not in upgrades[0].get("condition", ""):
            probs.append(f"{name} needs one conditional Apply Solution Upgrade step")

    build = jobs[("Build", "build")]
    order = [s.get("displayName", "") for s in build["steps"]]
    wanted = ["Gate - lint", "Stamp the version", "Pack unmanaged and managed", "Power Platform Checker"]
    idx = []
    for w in wanted:
        hits = [n for n, name in enumerate(order) if name.startswith(w)]
        if not hits:
            probs.append(f"Build is missing the step '{w}'")
        else:
            idx.append(hits[0])
    if idx != sorted(idx):
        probs.append("Build steps are out of order (lint, version, pack, checker)")
    checker = next((s for s in build["steps"] if s.get("task", "").endswith("PowerPlatformChecker@2")), None)
    if checker:
        i = checker["inputs"]
        if str(i.get("RuleSet")) != SOLUTION_CHECKER_RULESET:
            probs.append("Checker does not use the Solution checker rule set")
        if "_managed.zip" not in i.get("FilesToAnalyze", ""):
            probs.append("Checker must analyze the managed zip")
        if i.get("ErrorThreshold") is None or not str(i.get("ErrorLevel", "")).endswith("IssueCount"):
            probs.append("Checker needs ErrorLevel <level>IssueCount and an ErrorThreshold")
        if i.get("FailOnPowerAppsCheckerAnalysisError") is not True:
            probs.append("Checker must fail on analysis errors")
    if str(doc.get("name")) != "$(Date:yyyyMMdd)$(Rev:.r)":
        probs.append("run name must be $(Date:yyyyMMdd)$(Rev:.r): the version is stamped from it")
    version_steps = [s for s in build["steps"] if "Set-SolutionVersion.ps1" in script_of(s)]
    if not version_steps or "$(Build.BuildNumber)" not in script_of(version_steps[0]):
        probs.append("the version must be stamped from $(Build.BuildNumber)")
    return probs


def lint_export(pipeline_path, scripts_dir):
    """Rules that only make sense for export-solution-to-git.yml."""
    pipeline_path = Path(pipeline_path)
    probs = lint(pipeline_path, scripts_dir)
    doc = load(pipeline_path, defaults(yaml.safe_load(pipeline_path.read_text())))
    steps = doc["steps"]
    exports = [s for s in steps if s.get("task", "").endswith("PowerPlatformExportSolution@2")]
    by_managed = {s["inputs"].get("Managed"): s["inputs"]["SolutionOutputFile"] for s in exports}
    if set(by_managed) != {True, False}:
        probs.append("export must run once as unmanaged and once as managed")
    else:
        u, m = by_managed[False], by_managed[True]
        if m != u[: -len(".zip")] + "_managed.zip":
            probs.append(f"managed zip must be the unmanaged name plus _managed ({u} / {m})")
    unpack = [s for s in steps if s.get("task", "").endswith("PowerPlatformUnpackSolution@2")]
    if len(unpack) != 1:
        probs.append("exactly one unpack step expected")
    else:
        i = unpack[0]["inputs"]
        if i.get("SolutionType") != "Both":
            probs.append("unpack must use SolutionType Both")
        if by_managed.get(False) and i.get("SolutionInputFile") != by_managed[False]:
            probs.append("unpack must read the unmanaged zip (the managed one sits next to it)")
        if "$(sourceFolder)" in str(i.get("SolutionTargetFolder")) or "Build.SourcesDirectory" in str(i.get("SolutionTargetFolder")):
            probs.append("unpack must go to an empty temp folder, not into the repo (pac never deletes files)")
    texts = [script_of(s) for s in steps]
    if not any("Sync-SolutionSource.ps1" in t for t in texts):
        probs.append("the unpacked folder must go through Sync-SolutionSource.ps1")
    git = "\n".join(t for t in texts if "git push" in t)
    if not git:
        probs.append("nothing is pushed")
    if re.search(r"git push\s+\S+\s+(HEAD:)?(main|master)\b", git) or "git push" in git and 'export/' not in git:
        probs.append("the export must go to an export/ branch, never to main")
    checkout = next((s for s in steps if "checkout" in s), None)
    if not checkout or checkout.get("persistCredentials") is not True:
        probs.append("checkout needs persistCredentials: true to push")
    if doc.get("trigger") != "none":
        probs.append("the export is manual: trigger must be none")
    return probs
