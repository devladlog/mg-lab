from pathlib import Path

from agentfiles import cli, skilllint

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src" / "skills" / "vendor-intake-check" / "SKILL.md"

GOOD = "---\nname: my-skill\ndescription: Does one thing.\n---\n\nSteps here.\n"


def rules(text, folder=None):
    return {(f.level, f.rule) for f in skilllint.lint_text(text, folder)}


def test_our_skill_is_clean():
    assert skilllint.lint_file(SKILL) == []
    assert cli.main(["skill-lint", str(SKILL)]) == 0


def test_good_minimal_skill():
    assert rules(GOOD, "my-skill") == set()


def test_missing_front_matter():
    assert rules("# just markdown\n") == {("error", "front-matter")}


def test_unquoted_colon_is_invalid_yaml():
    # the exact example Learn gives: description: My: skill
    assert rules("---\nname: a\ndescription: My: skill\n---\nBody\n") == {("error", "front-matter")}
    assert rules('---\nname: a\ndescription: "My: skill"\n---\nBody\n') == set()


def test_missing_name_and_description():
    assert rules("---\nname: ''\n---\nBody\n") == {("error", "name"), ("error", "description")}


def test_name_rules_and_folder_match():
    r = rules("---\nname: My Skill\ndescription: x\n---\nBody\n", "other")
    assert ("warning", "name-format") in r and ("warning", "name-folder") in r


def test_multiline_description_is_a_warning():
    text = "---\nname: a\ndescription: |\n  line one\n  line two\n---\nBody\n"
    assert ("warning", "description-lines") in rules(text)


def test_length_limits():
    long_desc = "---\nname: a\ndescription: " + "x" * 1025 + "\n---\nBody\n"
    assert ("error", "description-length") in rules(long_desc)
    long_body = GOOD + "y" * 20_000
    assert ("error", "body-length") in rules(long_body, "my-skill")
    many_lines = GOOD + "\n".join(["line"] * 600)
    assert ("warning", "lines") in rules(many_lines, "my-skill")


def test_empty_body():
    assert ("error", "body") in rules("---\nname: a\ndescription: b\n---\n")


def test_bom_and_encoding(tmp_path):
    f = tmp_path / "my-skill" / "SKILL.md"
    f.parent.mkdir()
    f.write_bytes(b"\xef\xbb\xbf" + GOOD.encode())
    assert [x.rule for x in skilllint.lint_file(f)] == ["encoding"]
    f.write_bytes(b"---\nname: a\ndescription: \xff\xfe\n---\nx")
    assert [x.rule for x in skilllint.lint_file(f)] == ["encoding"]
    f.write_text(GOOD, encoding="utf-8")
    assert skilllint.lint_file(f) == []


def test_cli_fails_on_errors(tmp_path, capsys):
    f = tmp_path / "SKILL.md"
    f.write_text("no front matter", encoding="utf-8")
    assert cli.main(["skill-lint", str(f)]) == 1
    assert "FAIL" in capsys.readouterr().out
