from pathlib import Path

from agent_ready import instructions as ins


def make(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def codes(findings):
    return {(f.level, f.code) for f in findings}


def test_demo_repo_instructions_are_clean(demo):
    assert ins.check_repo(demo) == []


def test_missing_repo_instructions(tmp_path):
    repo = make(tmp_path, {"src/a.cs": ""})
    assert ("warning", "no-repo-instructions") in codes(ins.check_repo(repo))


def test_path_specific_file_needs_frontmatter_and_applyto(tmp_path):
    repo = make(tmp_path, {
        ".github/copilot-instructions.md": "Run `dotnet test`.\n",
        ".github/instructions/a.instructions.md": "# no frontmatter\n",
        ".github/instructions/b.instructions.md": "---\ndescription: x\n---\nrule\n",
    })
    c = codes(ins.check_repo(repo))
    assert ("error", "frontmatter") in c and ("error", "applyTo") in c


def test_applyto_that_matches_nothing_warns(tmp_path):
    repo = make(tmp_path, {
        ".github/copilot-instructions.md": "Run `dotnet test`.\n",
        ".github/instructions/a.instructions.md": '---\napplyTo: "lib/**/*.py"\n---\nrule\n',
        "src/a.cs": "",
    })
    assert ("warning", "applyTo-nomatch") in codes(ins.check_repo(repo))


def test_applyto_glob_forms(tmp_path):
    files = ["src/x/Foo.cs", "tests/Foo.Tests.cs", "web/a.tsx", "README.md"]
    assert ins._glob_matches("**/*.cs", files)
    assert ins._glob_matches("src/**/*.cs", files)
    assert ins._glob_matches("**/*.{tsx,jsx}", files)
    assert ins._glob_matches("*.md", files)
    assert not ins._glob_matches("*.cs", files)  # * does not cross folders
    assert not ins._glob_matches("docs/**", files)


def test_unsupported_review_instructions_are_flagged(tmp_path):
    body = ("Run `dotnet test`.\n- Use bold for every finding\n- Add emoji\n- Block the merge if tests fail\n"
            "- See https://example.com/style\n- Be more accurate\n- Update the pull request overview\n- Write a changelog entry\n")
    repo = make(tmp_path, {".github/copilot-instructions.md": body})
    found = [f for f in ins.check_repo(repo) if f.code == "unsupported-for-review"]
    assert len(found) == 6  # one per pattern: format (bold/emoji), overview, merge, changelog, link, vague


def test_no_test_command_warns(tmp_path):
    repo = make(tmp_path, {".github/copilot-instructions.md": "Be nice to the code.\n"})
    assert ("warning", "no-test-command") in codes(ins.check_repo(repo))


def test_big_file_warns(tmp_path):
    repo = make(tmp_path, {".github/copilot-instructions.md": "Run `dotnet test`.\n" + "line\n" * 1000})
    assert ("warning", "size") in codes(ins.check_repo(repo))


def test_agents_md_is_discovered(tmp_path):
    repo = make(tmp_path, {"AGENTS.md": "Use `dotnet test`.\n", ".github/copilot-instructions.md": "Run `dotnet test`.\n"})
    names = [p.name for p in ins.discover(repo)]
    assert "AGENTS.md" in names
