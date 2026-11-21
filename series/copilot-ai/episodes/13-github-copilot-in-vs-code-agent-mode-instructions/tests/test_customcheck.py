from pathlib import Path

import pytest

from customcheck import cli, frontmatter
from customcheck.convert import prompt_to_skill
from customcheck.globmatch import matches
from customcheck.rules import check_repo, explain


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def codes(report):
    return {f.code for f in report.findings}


# The table from the VS Code custom instructions reference (verified 21 Nov 2026)
@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("*.py", "app.py", True),
        ("*.py", "src/app.py", False),
        ("src/*.py", "src/app.py", True),
        ("src/*.py", "src/api/routes.py", False),
        ("src/**/*.py", "src/app.py", True),
        ("src/**/*.py", "src/api/routes.py", True),
        ("src/**/*.py", "tests/test_app.py", False),
        ("tests/**/*.py", "tests/test_app.py", True),
        ("tests/**/*.py", "tests/unit/test_app.py", True),
        ("tests/**/*.py", "src/app.py", False),
        ("**/*.ts, **/*.tsx", "web/a/b.tsx", True),
        ("**/*.ts, **/*.tsx", "web/a/b.js", False),
        ("**", "anything/at/all.txt", True),
        ("tests/**/*.py", "./tests/test_app.py", True),
    ],
)
def test_applyto_matches_documented_table(pattern, path, expected):
    assert matches(pattern, path) is expected


def test_frontmatter_variants():
    assert frontmatter.parse("plain text").meta is None
    ok = frontmatter.parse("---\napplyTo: '**'\n---\nBody")
    assert ok.meta == {"applyTo": "**"} and ok.body == "Body"
    assert frontmatter.parse("---\na: [\n---\nx").error.startswith("invalid YAML")
    assert "not closed" in frontmatter.parse("---\na: 1\nbody").error


def test_instruction_applyto_list_is_an_error_and_no_match_is_a_warning(tmp_path):
    write(tmp_path, "src/app.py", "x = 1\n")
    write(tmp_path, ".github/instructions/a.instructions.md", "---\napplyTo:\n  - '**/*.py'\n---\nRule\n")
    write(tmp_path, ".github/instructions/b.instructions.md", "---\napplyTo: 'docs/**/*.md'\n---\nRule\n")
    report = check_repo(tmp_path)
    by = {(f.code, f.path) for f in report.findings}
    assert ("APPLYTO_TYPE", ".github/instructions/a.instructions.md") in by
    assert ("APPLYTO_NO_MATCH", ".github/instructions/b.instructions.md") in by


def test_instruction_relative_pattern_and_wrong_suffix(tmp_path):
    write(tmp_path, "src/app.py", "")
    write(tmp_path, ".github/instructions/a.instructions.md", "---\napplyTo: '../src/*.py'\n---\nRule\n")
    write(tmp_path, ".github/instructions/notes.md", "Rule\n")
    assert {"APPLYTO_RELATIVE", "WRONG_SUFFIX"} <= codes(check_repo(tmp_path))


def test_description_only_instruction_is_local_only_note(tmp_path):
    write(tmp_path, ".github/instructions/a.instructions.md", "---\ndescription: Use when testing\n---\nRule\n")
    report = check_repo(tmp_path)
    assert "DESCRIPTION_ONLY" in codes(report)
    assert report.count("error") == 0


def test_project_files_duplicate_and_frontmatter_note(tmp_path):
    write(tmp_path, ".github/copilot-instructions.md", "---\nx: 1\n---\nRule\n")
    write(tmp_path, "AGENTS.md", "Rule\n")
    assert {"TWO_PROJECT_FILES", "FRONTMATTER_IGNORED"} <= codes(check_repo(tmp_path))


def test_skill_rules(tmp_path):
    write(tmp_path, ".github/skills/Bad_Name/SKILL.md", "---\nname: Bad_Name\ndescription: d\n---\nx\n")
    write(tmp_path, ".github/skills/good/SKILL.md", "---\nname: other\ndescription: d\n---\nx\n")
    write(tmp_path, ".github/skills/nodesc/SKILL.md", "---\nname: nodesc\n---\nx\n")
    write(tmp_path, ".github/skills/long/SKILL.md", "---\nname: long\ndescription: " + "a" * 1025 + "\n---\nx\n")
    write(tmp_path, ".github/skills/plugin/SKILL.md", "---\nname: 'my-org:plugin'\ndescription: d\n---\nx\n")
    write(tmp_path, ".github/skills/off/SKILL.md",
          "---\nname: off\ndescription: d\nuser-invocable: false\ndisable-model-invocation: true\ncontext: join\n---\nx\n")
    report = check_repo(tmp_path)
    by = {(f.code, f.path.split("/")[2]) for f in report.findings if f.path.startswith(".github/skills")}
    assert ("SKILL_NAME", "Bad_Name") in by
    assert ("SKILL_DIR", "good") in by
    assert ("SKILL_DESC", "nodesc") in by
    assert ("SKILL_DESC", "long") in by
    assert ("SKILL_NAME", "plugin") in by
    assert {("SKILL_DISABLED", "off"), ("SKILL_CONTEXT", "off")} <= by


def test_agent_rules(tmp_path):
    write(tmp_path, ".github/agents/old.chatmode.md", "---\ndescription: d\n---\nx\n")
    write(tmp_path, ".github/agents/a.agent.md",
          "---\nname: A\ntools: ['read', 'browser/open', 'nonsense']\ninfer: true\nhandoffs: []\nskills: [x]\n---\nx\n")
    write(tmp_path, ".github/agents/b.agent.md", "---\nname: B\n---\nx\n")
    codes_ = codes(check_repo(tmp_path))
    assert {"CHATMODE", "TOOL_UNKNOWN", "AGENT_INFER", "AGENT_LOCAL_ONLY", "AGENT_COPILOT_ONLY", "AGENT_NO_DESC"} <= codes_


def test_prompt_rules(tmp_path):
    write(tmp_path, ".github/agents/rev.agent.md", "---\nname: rev\ndescription: d\n---\nx\n")
    write(tmp_path, ".github/prompts/a.prompt.md",
          "---\nagent: nobody\nmode: agent\ntools: read\n---\nSee [x](../missing.md) and #file:../also-missing.md\n")
    write(tmp_path, ".github/prompts/b.prompt.md", "---\nagent: rev\n---\nBody\n")
    report = check_repo(tmp_path)
    by = [(f.code, f.path) for f in report.findings]
    assert ("AGENT_UNKNOWN", ".github/prompts/a.prompt.md") in by
    assert ("UNKNOWN_KEY", ".github/prompts/a.prompt.md") in by
    assert ("TOOLS_TYPE", ".github/prompts/a.prompt.md") in by
    assert by.count(("LINK_BROKEN", ".github/prompts/a.prompt.md")) == 2
    assert ("AGENT_UNKNOWN", ".github/prompts/b.prompt.md") not in by
    assert sum(1 for c, _ in by if c == "PROMPT_LOCAL_ONLY") == 2


def test_explain_lists_project_and_matching_targeted_files(tmp_path):
    write(tmp_path, ".github/copilot-instructions.md", "Rule\n")
    write(tmp_path, ".github/instructions/t.instructions.md", "---\napplyTo: 'tests/**/*.py'\n---\nR\n")
    assert len(explain(tmp_path, "tests/unit/test_x.py")) == 2
    assert len(explain(tmp_path, "src/x.py")) == 1


def test_convert_prompt_to_skill_rebases_links_and_reports_losses(tmp_path):
    write(tmp_path, ".github/copilot-instructions.md", "Rule\n")
    prompt = write(
        tmp_path,
        ".github/prompts/Weekly_Report.prompt.md",
        "---\ndescription: Weekly report\nargument-hint: '[days]'\nagent: agent\nmodel: gpt-x\ntools: ['execute']\n---\n"
        "Run it for ${input:days:7}. Follow [rules](../copilot-instructions.md).\n",
    )
    result = prompt_to_skill(prompt, tmp_path / ".github" / "skills")
    text = result.skill_file.read_text(encoding="utf-8")
    parsed = frontmatter.parse(text)
    assert result.skill_dir.name == "weekly-report"
    assert parsed.meta["name"] == "weekly-report"
    assert parsed.meta["disable-model-invocation"] is True
    assert parsed.meta["argument-hint"] == "[days]"
    assert "agent" not in parsed.meta and "tools" not in parsed.meta
    assert "(../../copilot-instructions.md)" in parsed.body
    joined = " ".join(result.notes)
    assert "'agent: agent'" in joined and "'model: gpt-x'" in joined and "'tools:" in joined and "${input:" in joined
    # The converted skill passes the linter and the original is untouched
    assert check_repo(tmp_path).count("error") == 0
    assert prompt.exists()


def test_convert_refuses_to_overwrite(tmp_path):
    prompt = write(tmp_path, ".github/prompts/a.prompt.md", "---\ndescription: d\n---\nBody\n")
    prompt_to_skill(prompt, tmp_path / ".github" / "skills")
    with pytest.raises(FileExistsError):
        prompt_to_skill(prompt, tmp_path / ".github" / "skills")


def test_convert_without_description_uses_first_line(tmp_path):
    prompt = write(tmp_path, ".github/prompts/a.prompt.md", "Summarise the open issues.\nMore.\n")
    result = prompt_to_skill(prompt, tmp_path / ".github" / "skills")
    assert "Summarise the open issues." in result.skill_file.read_text(encoding="utf-8")
    assert any("first line" in n for n in result.notes)


def test_cli_exit_codes(tmp_path, capsys):
    write(tmp_path, ".github/skills/x/SKILL.md", "---\nname: x\n---\nb\n")
    assert cli.main(["check", str(tmp_path)]) == 1
    clean = tmp_path / "clean"
    write(clean, ".github/copilot-instructions.md", "Rule\n")
    assert cli.main(["check", str(clean)]) == 0
    write(clean, ".github/instructions/a.instructions.md", "---\napplyTo: 'nothing/**'\n---\nR\n")
    assert cli.main(["check", str(clean)]) == 0
    assert cli.main(["check", str(clean), "--strict"]) == 1
    capsys.readouterr()
    assert cli.main(["check", str(clean), "--json"]) == 0
    assert '"APPLYTO_NO_MATCH"' in capsys.readouterr().out
