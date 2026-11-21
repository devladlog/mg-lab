import csv
import io
from pathlib import Path

import pytest

from kbpack import docbuild, testset
from kbpack.cli import main

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "knowledge"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs")
    docbuild.build_all(SRC, out)
    return out


def test_sources_have_front_matter_and_libraries():
    sources = docbuild.load_sources(SRC)
    assert len(sources) == 5
    assert {s.library for s in sources} == {"Policies", "Restricted"}
    assert [s.library for s in sources if s.docx_name.endswith("restricted.docx")] == ["Restricted"]


def test_missing_front_matter_is_rejected(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# no front matter\n")
    with pytest.raises(ValueError, match="front matter"):
        docbuild.load_source(p)


def test_docx_has_title_heading_table_and_metadata(built):
    from docx import Document
    d = Document(str(built / "Policies" / "vendor-onboarding-policy.docx"))
    assert d.paragraphs[0].style.name == "Heading 1" and d.paragraphs[0].text == "Contoso Vendor Onboarding Policy"
    assert d.core_properties.title == "Contoso Vendor Onboarding Policy"
    assert len(d.tables) == 1 and d.tables[0].cell(2, 1).text == "Procurement manager"
    assert "25,000 euros and above" in docbuild.docx_text(built / "Policies" / "vendor-onboarding-policy.docx")


def test_build_is_reproducible(tmp_path):
    a = docbuild.build_all(SRC, tmp_path / "a")["Policies"][0]
    b = docbuild.build_all(SRC, tmp_path / "b")["Policies"][0]
    from docx import Document
    assert Document(str(a)).core_properties.created == Document(str(b)).core_properties.created
    assert docbuild.docx_text(a) == docbuild.docx_text(b)


def test_every_expected_fact_is_in_its_document(built):
    assert testset.check_facts(docbuild.load_sources(SRC), built) == []


def test_a_changed_policy_breaks_the_fact_check(built, tmp_path):
    sources = docbuild.load_sources(SRC)
    sources[0].faq[0]["facts"].append("a fact that is not in the document")
    problems = testset.check_facts(sources, built)
    assert len(problems) == 1 and "not in the document" in problems[0]


def test_testset_csv_matches_the_learn_import_format(built):
    sources = docbuild.load_sources(SRC)
    rows = testset.cases(sources, library="Policies") + [(q, testset.NO_ANSWER) for q in testset.OUT_OF_SCOPE]
    text = testset.to_csv(rows)
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == ["Question", "Expected response"]
    assert len(parsed) - 1 == 11 <= testset.MAX_QUESTIONS
    assert all(len(r[0]) <= testset.MAX_QUESTION_CHARS for r in parsed[1:])


def test_restricted_questions_are_kept_apart():
    sources = docbuild.load_sources(SRC)
    assert len(testset.cases(sources, library="Restricted")) == 1
    assert not any("12 percent" in a for _, a in testset.cases(sources, library="Policies"))


def test_validate_catches_limit_violations():
    assert testset.validate([("q" * 1001, "a")]) == ["row 1: question has 1001 characters; the limit is 1000"]
    assert any("101 questions" in p for p in testset.validate([(f"q{i}", "a") for i in range(101)]))
    assert any("duplicate" in p for p in testset.validate([("Same?", "a"), ("same?", "b")]))
    assert any("no expected response" in p for p in testset.validate([("q", "")]))
    with pytest.raises(ValueError):
        testset.to_csv([])


def test_conversation_format_checks():
    ok = "conversationNumber,question,response\n1,What?,Answer\n1,And?,\n2,Next?,A\n"
    assert testset.validate_conversation_csv(ok) == []
    assert testset.validate_conversation_csv("question,response\nx,y\n")[0].startswith("header")
    many = "conversationNumber,question\n" + "".join(f"1,q{i}\n" for i in range(7))
    assert any("limit is 6" in p for p in testset.validate_conversation_csv(many))
    toomany = "conversationNumber,question\n" + "".join(f"{i},q\n" for i in range(21))
    assert any("limit is 20" in p for p in testset.validate_conversation_csv(toomany))
    assert any("whole number" in p for p in testset.validate_conversation_csv("conversationNumber,question\na,q\n"))


def test_cli_build_check_testset(tmp_path, capsys):
    assert main(["build", "--out", str(tmp_path / "docs")]) == 0
    assert "Policies/vendor-onboarding-policy.docx" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "docs" / "Policies")]) == 0
    assert "READY" in capsys.readouterr().out
    assert main(["testset", "--docs", str(tmp_path / "docs"), "--out", str(tmp_path / "ts")]) == 0
    assert (tmp_path / "ts" / "vendor-desk-testset.csv").read_text().startswith("Question,Expected response")


def test_cli_check_exit_codes(tmp_path, capsys):
    (tmp_path / "x.txt").write_text("x")
    assert main(["check", str(tmp_path)]) == 1
    assert "NOT READY" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "missing")]) == 2
