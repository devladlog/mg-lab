#!/usr/bin/env python3
"""Team rules for Dockerfile, .dockerignore and compose.yaml, checked without a Docker daemon.

A small, readable subset of what hadolint and `docker compose config` do, plus our own rules.
Run it in CI next to the real tools, or alone where Docker isn't available:

    python3 tools/container_lint.py            # all three files in the current folder
    python3 tools/container_lint.py dockerfile path/to/Dockerfile
    python3 tools/container_lint.py context .  # list what the build context would contain

Exit code 1 if any rule with severity "error" fails.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SECRET_NAME = re.compile(r"(?i)(password|passwd|secret|token|api_?key|access_?key)")


@dataclass
class Finding:
    rule: str
    severity: str  # "error" | "warning"
    line: int
    message: str

    def __str__(self) -> str:
        return f"{'✗' if self.severity == 'error' else '!'} {self.rule} (line {self.line}): {self.message}"


@dataclass
class Instruction:
    line: int
    keyword: str
    args: str
    flags: dict = field(default_factory=dict)


@dataclass
class Stage:
    image: str
    name: str | None
    line: int
    instructions: list[Instruction] = field(default_factory=list)


# --------------------------------------------------------------------------------------- Dockerfile
def parse_dockerfile(text: str) -> list[Stage]:
    """Instructions grouped by stage. Handles comments, parser directives and backslash continuations."""
    stages: list[Stage] = []
    logical, start = "", 0
    for no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not logical and (not stripped or stripped.startswith("#")):
            continue
        if logical and stripped.startswith("#"):  # comment inside a continued instruction
            continue
        if not logical:
            start = no
        if stripped.endswith("\\"):
            logical += stripped[:-1] + " "
            continue
        logical += stripped
        keyword, _, rest = logical.partition(" ")
        keyword, rest = keyword.upper(), rest.strip()
        flags = {}
        while rest.startswith("--"):
            flag, _, rest = rest.partition(" ")
            name, _, value = flag[2:].partition("=")
            flags.setdefault(name, []).append(value)
            rest = rest.strip()
        ins = Instruction(start, keyword, rest, flags)
        if keyword == "FROM":
            m = re.match(r"(\S+)(?:\s+AS\s+(\S+))?", rest, re.IGNORECASE)
            stages.append(Stage(m.group(1), m.group(2), start))
        if stages:
            stages[-1].instructions.append(ins)
        logical = ""
    return stages


def lint_dockerfile(text: str, app_port: int = 8080) -> list[Finding]:
    stages = parse_dockerfile(text)
    out: list[Finding] = []
    if not stages:
        return [Finding("DF000", "error", 1, "no FROM instruction")]
    names = {s.name for s in stages if s.name}

    for s in stages:
        if s.image in names:
            continue  # FROM an earlier stage
        repo_tag = s.image.split("@")[0]
        tag = repo_tag.rsplit(":", 1)[1] if ":" in repo_tag.rsplit("/", 1)[-1] else None
        if tag in (None, "latest"):
            out.append(Finding("DF001", "error", s.line, f"{s.image}: use a version tag, not latest"))
        if "@sha256:" not in s.image:
            out.append(
                Finding(
                    "DF002",
                    "warning",
                    s.line,
                    f"{s.image}: pin the digest too (tag@sha256:...) for reproducible builds",
                )
            )

    final = stages[-1]
    if "/dotnet/sdk" in final.image:
        out.append(Finding("DF003", "error", final.line, "the SDK image ships: use a multi-stage build"))
    if len(stages) < 2:
        out.append(Finding("DF003", "error", final.line, "single-stage build: build tools end up in the image"))

    users = [i for i in final.instructions if i.keyword == "USER"]
    if not users or users[-1].args.split(":")[0] in ("root", "0"):
        out.append(
            Finding(
                "DF004",
                "error",
                (users[-1].line if users else final.line),
                "runs as root: add USER $APP_UID to the final stage",
            )
        )

    for s in stages:
        for i in s.instructions:
            if i.keyword == "ADD" and not re.search(r"https?://|\.tar(\.\w+)?\b|\.tgz\b", i.args):
                out.append(
                    Finding("DF005", "error", i.line, "use COPY for local files; ADD also unpacks and downloads")
                )
            if i.keyword in ("ENV", "ARG"):
                for name in re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)(?==|\s|$)", i.args):
                    if SECRET_NAME.search(name):
                        out.append(
                            Finding("DF006", "error", i.line, f"{name}: secrets in ENV/ARG stay in the image history")
                        )
                if re.search(r"(?i)(password|pwd)\s*=\s*[^;\s\"$]", i.args):
                    out.append(
                        Finding("DF006", "error", i.line, "password in a connection string baked into the image")
                    )
            if i.keyword in ("ENTRYPOINT", "CMD") and not i.args.startswith("["):
                out.append(
                    Finding(
                        "DF007", "error", i.line, f"{i.keyword} in shell form: /bin/sh -c won't pass SIGTERM to the app"
                    )
                )

    build = next((s for s in stages if any("dotnet restore" in i.args for i in s.instructions)), None)
    if build:
        copies = [i for i in build.instructions if i.keyword == "COPY" and "from" not in i.flags]
        restore = next(i for i in build.instructions if "dotnet restore" in i.args)
        source_copy = next(
            (c for c in copies if not re.search(r"\.(csproj|fsproj|sln|slnx|json|props)\b", c.args)), None
        )
        if not any(".csproj" in c.args and c.line < restore.line for c in copies):
            out.append(Finding("DF008", "error", restore.line, "copy the project file(s) before restore"))
        if source_copy and source_copy.line < restore.line:
            out.append(
                Finding(
                    "DF008", "error", source_copy.line, "source copied before restore: every edit re-downloads packages"
                )
            )

    exposed = [i for i in final.instructions if i.keyword == "EXPOSE"]
    ports = {int(p.split("/")[0]) for i in exposed for p in i.args.split()}
    if app_port not in ports:
        out.append(Finding("DF009", "warning", final.line, f"final stage doesn't EXPOSE {app_port}"))
    if any(p < 1024 for p in ports):
        out.append(Finding("DF009", "error", exposed[0].line, "port below 1024 needs root; .NET uses 8080"))
    return sorted(out, key=lambda f: f.line)


# --------------------------------------------------------------------------------------- .dockerignore
def _pattern_regex(pattern: str) -> re.Pattern:
    """.dockerignore pattern -> regex (Go filepath.Match rules plus **, relative to the context root)."""
    p = pattern.strip("/")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += r"(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(f"^{out}$")


def read_dockerignore(text: str) -> list[tuple[bool, re.Pattern, str]]:
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        rules.append((negate, _pattern_regex(line.lstrip("!")), line))
    return rules


def is_ignored(rel_path: str, rules) -> bool:
    """Last matching rule wins; a path is also excluded when one of its parent folders matches."""
    parts = rel_path.split("/")
    candidates = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    ignored = False
    for negate, rx, _ in rules:
        if any(rx.match(c) for c in candidates):
            ignored = not negate
    return ignored


def build_context(root: Path, dockerignore: Path | None = None) -> list[str]:
    dockerignore = dockerignore or root / ".dockerignore"
    rules = read_dockerignore(dockerignore.read_text()) if dockerignore.exists() else []
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if not is_ignored(rel, rules):
                files.append(rel)
    return files


def lint_context(root: Path) -> list[Finding]:
    out = []
    files = build_context(root)
    must_exclude = {
        r"(^|/)bin/": "build output (bin/)",
        r"(^|/)obj/": "build output (obj/)",
        r"^\.git/": ".git history",
        r"(^|/)\.env$": ".env secrets",
        r"^tests/": "test projects",
    }
    for rx, what in must_exclude.items():
        leaked = [f for f in files if re.search(rx, f)]
        if leaked:
            out.append(Finding("DI001", "error", 0, f"{what} would be sent to the builder: {leaked[0]}"))
    return out


# --------------------------------------------------------------------------------------- compose.yaml
def lint_compose(doc: dict, app_port: int = 8080) -> list[Finding]:
    out: list[Finding] = []
    services = doc.get("services", {})
    declared_volumes = set((doc.get("volumes") or {}).keys())
    for name, svc in services.items():
        for port in svc.get("ports", []):
            spec = (
                port
                if isinstance(port, str)
                else f"{port.get('host_ip', '')}:{port.get('published')}:{port.get('target')}"
            )
            if not spec.startswith("127.0.0.1:"):
                out.append(
                    Finding(
                        "DC001",
                        "error",
                        0,
                        f"{name}: port {spec} is published on every interface; bind to 127.0.0.1 for local development",
                    )
                )
        env = svc.get("environment", {})
        env = dict(e.split("=", 1) if "=" in e else (e, None) for e in env) if isinstance(env, list) else env
        for key, value in env.items():
            text = str(value or "")
            for m in re.finditer(r"(?i)(password|pwd)\s*=\s*([^;]*)", text):
                if not m.group(2).startswith("${"):
                    out.append(Finding("DC002", "error", 0, f"{name}.{key}: literal password in compose file"))
            if SECRET_NAME.search(key) and text and not text.startswith("${"):
                out.append(Finding("DC002", "error", 0, f"{name}.{key}: literal secret in compose file"))
            for var in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)([^}]*)\}", text):
                if SECRET_NAME.search(var[0]) and not var[1].startswith(":?"):
                    out.append(
                        Finding(
                            "DC003",
                            "error",
                            0,
                            f"{name}.{key}: use ${{{var[0]}:?message}} so a missing secret stops "
                            "Compose instead of becoming an empty string",
                        )
                    )
        for dep, cond in (svc.get("depends_on") or {}).items() if isinstance(svc.get("depends_on"), dict) else []:
            target = services.get(dep, {})
            if cond.get("condition") == "service_healthy" and "healthcheck" not in target:
                out.append(
                    Finding("DC004", "error", 0, f"{name} waits for {dep} to be healthy, but {dep} has no healthcheck")
                )
        if isinstance(svc.get("depends_on"), list):
            out.append(
                Finding(
                    "DC004",
                    "warning",
                    0,
                    f"{name}: short depends_on only waits for the container to start, not to be ready",
                )
            )
        for vol in svc.get("volumes", []):
            source = vol.split(":")[0] if isinstance(vol, str) else vol.get("source", "")
            if source and not source.startswith((".", "/", "~", "$")) and source not in declared_volumes:
                out.append(Finding("DC005", "error", 0, f"{name}: named volume '{source}' is not declared"))
        image = svc.get("image", "")
        if image and "build" not in svc and (":" not in image.rsplit("/", 1)[-1]):
            out.append(Finding("DC006", "error", 0, f"{name}: image {image} has no tag"))
        hc = svc.get("healthcheck", {}).get("test")
        if isinstance(hc, list) and hc[0] == "CMD-SHELL" and re.search(r"(?<!\$)\$(?!\$)\{?[A-Z_]*PASSWORD", hc[1]):
            out.append(
                Finding(
                    "DC007",
                    "warning",
                    0,
                    f"{name}: healthcheck uses $VAR (Compose interpolates it into the file); "
                    "use $$VAR so the container's own variable is read",
                )
            )
    return out


# --------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "what", nargs="?", default="all", choices=["all", "dockerfile", "compose", "dockerignore", "context"]
    )
    ap.add_argument("path", nargs="?", default=".")
    args = ap.parse_args(argv)
    root = Path(args.path)
    findings: list[tuple[str, Finding]] = []

    if args.what == "context":
        for f in build_context(root if root.is_dir() else root.parent):
            print(f)
        return 0
    if args.what in ("all", "dockerfile"):
        df = root / "Dockerfile" if root.is_dir() else root
        findings += [(df.name, f) for f in lint_dockerfile(df.read_text())]
    if args.what in ("all", "dockerignore"):
        findings += [(".dockerignore", f) for f in lint_context(root if root.is_dir() else root.parent)]
    if args.what in ("all", "compose"):
        import yaml  # PyYAML; only needed for this check

        cf = root / "compose.yaml" if root.is_dir() else root
        findings += [("compose.yaml", f) for f in lint_compose(yaml.safe_load(cf.read_text()))]

    for file, f in findings:
        print(f"{file}: {f}" if args.what == "all" else str(f))
    errors = sum(f.severity == "error" for _, f in findings)
    warnings = len(findings) - errors
    print(f"{'✓' if not errors else '✗'} {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
