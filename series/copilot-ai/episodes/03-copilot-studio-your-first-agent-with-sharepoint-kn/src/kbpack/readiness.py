"""Check a folder of documents against the documented limits of a Copilot Studio SharePoint knowledge source.

Nothing here talks to SharePoint: it checks the files *before* you upload them, so the agent does not silently
return "no response" later. Every finding names the Learn page it comes from.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from . import limits as L

ERROR, WARN, INFO = "error", "warning", "info"


@dataclass
class Finding:
    severity: str
    path: str
    rule: str
    message: str
    source: str = ""


@dataclass
class Report:
    mode: str
    m365_copilot: bool
    files_checked: int = 0
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == WARN)

    @property
    def ok(self) -> bool:
        return self.errors == 0


def _fmt_mb(n: int) -> str:
    return f"{n / L.MB:.1f} MB"


def _ooxml_is_encrypted(path: Path) -> bool:
    """A password-protected .docx/.pptx/.xlsx is not a ZIP: it is an OLE compound file holding EncryptedPackage."""
    with path.open("rb") as fh:
        return fh.read(8) == L.OLE_MAGIC


def _pdf_is_encrypted(path: Path) -> bool:
    from pypdf import PdfReader
    try:
        return bool(PdfReader(str(path)).is_encrypted)
    except Exception:  # unreadable PDF: report it as encrypted/unreadable rather than crash
        return True


def _sensitivity_labels(path: Path) -> List[str]:
    """Names of Microsoft Purview sensitivity labels stamped in docProps/custom.xml (MSIP_Label_<guid>_Name)."""
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/custom.xml" not in z.namelist():
                return []
            xml = z.read("docProps/custom.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, OSError):
        return []
    import re
    names = []
    for m in re.finditer(r'name="MSIP_Label_[0-9a-fA-F-]+_Name"[^>]*>\s*<vt:lpwstr>([^<]*)</vt:lpwstr>', xml):
        names.append(m.group(1))
    return names


def _docx_has_title(path: Path) -> bool:
    """True when the first non-empty paragraph is a Title or Heading 1 (so the topic is in the text, not only in the name)."""
    from docx import Document
    try:
        doc = Document(str(path))
    except Exception:
        return True  # not our business here; the encryption/corruption checks speak up
    for p in doc.paragraphs:
        if p.text.strip():
            return p.style.name in ("Title", "Heading 1")
    return False


def check_folder(root: Path, *, mode: str = "site", m365_copilot: bool = False) -> Report:
    """mode 'site': the SharePoint option (URL of site or folder). mode 'files': Upload files > SharePoint."""
    if mode not in ("site", "files"):
        raise ValueError("mode must be 'site' or 'files'")
    root = Path(root)
    rep = Report(mode=mode, m365_copilot=m365_copilot)
    allowed = L.SITE_TYPES if mode == "site" else L.FILES_TYPES
    src = L.SITE_URL if mode == "site" else L.FILES_URL
    max_bytes = (L.SITE_MAX_BYTES_M365 if m365_copilot else L.SITE_MAX_BYTES_NO_M365) if mode == "site" \
        else L.FILES_MAX_BYTES

    files = sorted(p for p in root.rglob("*") if p.is_file())
    folders = sorted({p.parent for p in files if p.parent != root})
    rep.files_checked = len(files)

    if mode == "files":
        deepest = max((len(p.relative_to(root).parts) - 1 for p in files), default=0)
        if len(files) > L.FILES_MAX_FILES:
            rep.findings.append(Finding(ERROR, ".", "file-count",
                                        f"{len(files)} files; one source holds at most {L.FILES_MAX_FILES}.", src))
        if len(folders) > L.FILES_MAX_FOLDERS:
            rep.findings.append(Finding(ERROR, ".", "folder-count",
                                        f"{len(folders)} folders; one source holds at most {L.FILES_MAX_FOLDERS}.", src))
        if deepest > L.FILES_MAX_DEPTH:
            rep.findings.append(Finding(ERROR, ".", "depth",
                                        f"{deepest} levels of subfolders; the limit is {L.FILES_MAX_DEPTH}.", src))

    for p in files:
        rel = str(p.relative_to(root))
        ext = p.suffix.lower()
        size = p.stat().st_size

        if ext == ".aspx":
            rep.findings.append(Finding(ERROR, rel, "classic-page",
                                        "Content from classic .aspx pages is not used to generate answers.", L.SITE_URL))
            continue
        if ext in L.SITE_WEAK_TYPES and mode == "site":
            rep.findings.append(Finding(WARN, rel, "spreadsheet",
                                        "Excel files can be added, but the agent cannot run code, so analytical "
                                        "questions (sums, counts) may be answered badly.", L.SITE_URL))
        elif ext not in allowed:
            rep.findings.append(Finding(ERROR, rel, "file-type",
                                        f"'{ext or 'no extension'}' is not a supported type for this option "
                                        f"({', '.join(sorted(allowed))}); the file is ignored.", src))
            continue

        if size > max_bytes:
            hint = ""
            if mode == "site" and not m365_copilot:
                hint = (" Without a Microsoft 365 Copilot licence in the agent's tenant the limit is 7 MB: "
                        "split the file, or use Upload files (512 MB).")
            rep.findings.append(Finding(ERROR, rel, "file-size",
                                        f"{_fmt_mb(size)} is above the {_fmt_mb(max_bytes)} limit.{hint}", src))

        if ext in L.OOXML and _ooxml_is_encrypted(p):
            rep.findings.append(Finding(ERROR, rel, "password-protected",
                                        "Password-protected Office file: it can show as Ready and still return "
                                        "'no response'.", L.TROUBLE_URL))
        elif ext == ".pdf" and _pdf_is_encrypted(p):
            rep.findings.append(Finding(ERROR, rel, "password-protected",
                                        "Encrypted or unreadable PDF: the agent cannot ground on it.", L.TROUBLE_URL))

        if ext in L.OOXML and not _ooxml_is_encrypted(p):
            labels = _sensitivity_labels(p)
            if labels:
                rep.findings.append(Finding(WARN, rel, "sensitivity-label",
                                            f"Carries sensitivity label '{labels[0]}'. If the label applies "
                                            "encryption the agent cannot read the file (Learn: 'no response').",
                                            L.TROUBLE_URL))
            if ext == ".docx" and not _docx_has_title(p):
                rep.findings.append(Finding(WARN, rel, "no-title",
                                            "Does not start with a Title or Heading 1. Questions that name a file "
                                            "cannot be answered, so put the document's subject in its first line.",
                                            L.SITE_URL))
    return rep


def format_report(rep: Report) -> str:
    lines = [f"Knowledge readiness ({'SharePoint site/folder URL' if rep.mode == 'site' else 'Upload files > SharePoint'}, "
             f"Microsoft 365 Copilot licence in tenant: {'yes' if rep.m365_copilot else 'no'})",
             f"Files checked: {rep.files_checked}"]
    for f in rep.findings:
        lines.append(f"  [{f.severity.upper():7}] {f.path}: {f.message}  ({f.rule})")
    lines.append(f"Result: {rep.errors} error(s), {rep.warnings} warning(s) -> "
                 f"{'READY' if rep.ok else 'NOT READY'}")
    return "\n".join(lines)
