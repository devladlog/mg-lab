import zipfile
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from kbpack import docbuild, limits as L, readiness

ROOT = Path(__file__).resolve().parents[1]
MB = L.MB


def make_docx(path: Path, title: str | None = "A title", body: str = "Some text.") -> Path:
    d = Document()
    if title:
        d.add_heading(title, level=1)
    d.add_paragraph(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))
    return path


def rules(rep):
    return {(f.path, f.rule, f.severity) for f in rep.findings}


def test_the_episode_knowledge_pack_is_ready(tmp_path):
    docbuild.build_all(ROOT / "src" / "knowledge", tmp_path)
    for mode in ("site", "files"):
        rep = readiness.check_folder(tmp_path, mode=mode)
        assert rep.ok and rep.warnings == 0 and rep.files_checked == 5, readiness.format_report(rep)


def test_unsupported_types_are_errors_in_both_modes(tmp_path):
    for name in ("notes.txt", "readme.md", "clip.mp4", "archive.zip"):
        (tmp_path / name).write_bytes(b"x")
    for mode in ("site", "files"):
        rep = readiness.check_folder(tmp_path, mode=mode)
        assert rep.errors == 4
        assert {f.rule for f in rep.findings} == {"file-type"}


def test_excel_is_a_warning_on_site_but_fine_for_upload(tmp_path):
    (tmp_path / "prices.xlsx").write_bytes(b"PK\x03\x04")  # content irrelevant: type rule only
    site = readiness.check_folder(tmp_path, mode="site")
    assert ("prices.xlsx", "spreadsheet", "warning") in rules(site) and site.ok
    files = readiness.check_folder(tmp_path, mode="files")
    assert not [f for f in files.findings if f.rule == "spreadsheet"]


def test_classic_aspx_page_is_an_error(tmp_path):
    (tmp_path / "old.aspx").write_text("<html/>")
    rep = readiness.check_folder(tmp_path, mode="site")
    assert ("old.aspx", "classic-page", "error") in rules(rep)


@pytest.mark.parametrize("licence,limit_mb,expect_error", [(False, 7, True), (True, 200, False)])
def test_site_size_limit_depends_on_the_m365_copilot_licence(tmp_path, licence, limit_mb, expect_error):
    f = make_docx(tmp_path / "big.docx")
    with f.open("ab") as fh:           # trailing bytes after the zip: still a readable .docx, but 8 MB
        fh.write(b"\0" * (8 * MB))
    rep = readiness.check_folder(tmp_path, mode="site", m365_copilot=licence)
    sizes = [x for x in rep.findings if x.rule == "file-size"]
    assert bool(sizes) is expect_error
    if expect_error:
        assert "7.0 MB" in sizes[0].message and "split" in sizes[0].message


def test_files_mode_allows_up_to_512_mb_and_does_not_hint_about_7_mb(tmp_path):
    f = make_docx(tmp_path / "big.docx")
    with f.open("ab") as fh:
        fh.write(b"\0" * (8 * MB))
    assert readiness.check_folder(tmp_path, mode="files").ok


def test_password_protected_office_file_is_detected_by_its_ole_header(tmp_path):
    p = tmp_path / "secret.docx"
    p.write_bytes(L.OLE_MAGIC + b"\0" * 512)     # how an encrypted OOXML package starts: an OLE container, not a zip
    rep = readiness.check_folder(tmp_path)
    assert ("secret.docx", "password-protected", "error") in rules(rep)
    assert not any(f.rule == "no-title" for f in rep.findings)


def test_encrypted_pdf_is_detected(tmp_path):
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt("pw")
    with (tmp_path / "locked.pdf").open("wb") as fh:
        w.write(fh)
    plain = PdfWriter()
    plain.add_blank_page(width=200, height=200)
    with (tmp_path / "open.pdf").open("wb") as fh:
        plain.write(fh)
    rep = readiness.check_folder(tmp_path)
    assert ("locked.pdf", "password-protected", "error") in rules(rep)
    assert not any(f.path == "open.pdf" for f in rep.findings)


def test_sensitivity_label_is_a_warning_with_the_label_name(tmp_path):
    f = make_docx(tmp_path / "labelled.docx")
    custom = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
              'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
              '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" '
              'name="MSIP_Label_00000000-0000-0000-0000-000000000000_Name"><vt:lpwstr>Highly Confidential</vt:lpwstr>'
              '</property></Properties>')
    with zipfile.ZipFile(f, "a") as z:
        z.writestr("docProps/custom.xml", custom)
    rep = readiness.check_folder(tmp_path)
    hit = [x for x in rep.findings if x.rule == "sensitivity-label"]
    assert hit and "Highly Confidential" in hit[0].message and rep.ok  # a warning, not an error


def test_document_without_a_title_gets_a_warning(tmp_path):
    make_docx(tmp_path / "untitled.docx", title=None, body="Just a paragraph.")
    rep = readiness.check_folder(tmp_path)
    assert ("untitled.docx", "no-title", "warning") in rules(rep)


def test_files_mode_counts_files_folders_and_depth(tmp_path):
    deep = tmp_path
    for i in range(11):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "a.pdf").write_bytes(b"%PDF-1.4")
    rep = readiness.check_folder(tmp_path, mode="files")
    assert ("." , "depth", "error") in rules(rep)

    flat = tmp_path / "flat"
    for i in range(51):
        (flat / f"f{i}").mkdir(parents=True)
        (flat / f"f{i}" / "a.docx").write_bytes(b"PK")
    rep2 = readiness.check_folder(flat, mode="files")
    assert ("." , "folder-count", "error") in rules(rep2)


def test_bad_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        readiness.check_folder(tmp_path, mode="everything")


def test_every_finding_names_its_learn_source(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.aspx").write_text("x")
    (tmp_path / "c.docx").write_bytes(L.OLE_MAGIC)
    rep = readiness.check_folder(tmp_path)
    assert rep.findings and all(f.source.startswith("https://learn.microsoft.com/") for f in rep.findings)
