"""Build the evaluation test set for Copilot Studio from the FAQ pairs in the document front matter.

Format (Learn, 'Create a single response test set' > 'Create a test set file to import'): a CSV or TXT file, header
row 'Question' then 'Expected response', up to 100 questions, each question up to 1,000 characters.
https://learn.microsoft.com/microsoft-copilot-studio/analytics-agent-evaluation-create#create-a-test-set-file-to-import

The conversation format of the newer experience (conversationNumber,question,response; up to 20 conversations of up
to 6 questions) is checked by validate_conversation_csv for completeness.
https://learn.microsoft.com/microsoft-365/copilot-managed-runtime/developer/agents/cli/evaluate
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from .docbuild import Source, docx_text

MAX_QUESTIONS = 100
MAX_QUESTION_CHARS = 1000
HEADER = ["Question", "Expected response"]
NO_ANSWER = "I'm not sure how to help with that. Can you try rephrasing?"

# Questions the knowledge cannot answer. Expected: the agent declines instead of inventing something.
OUT_OF_SCOPE = [
    "What is the capital of Australia?",
    "How many vacation days does a Contoso employee get?",
]


def cases(sources: Iterable[Source], *, library: str | None = None) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for s in sources:
        if library is not None and s.library != library:
            continue
        for item in s.faq:
            out.append((str(item["q"]).strip(), str(item["a"]).strip()))
    return out


def validate(rows: Sequence[Tuple[str, str]]) -> List[str]:
    problems: List[str] = []
    if not rows:
        problems.append("test set is empty")
    if len(rows) > MAX_QUESTIONS:
        problems.append(f"{len(rows)} questions; the import allows {MAX_QUESTIONS}")
    seen = set()
    for i, (q, a) in enumerate(rows, 1):
        if not q:
            problems.append(f"row {i}: empty question")
        if len(q) > MAX_QUESTION_CHARS:
            problems.append(f"row {i}: question has {len(q)} characters; the limit is {MAX_QUESTION_CHARS}")
        if q.lower() in seen:
            problems.append(f"row {i}: duplicate question")
        seen.add(q.lower())
        if not a:
            problems.append(f"row {i}: no expected response (Compare meaning, Text similarity and Exact match need one)")
    return problems


def to_csv(rows: Sequence[Tuple[str, str]]) -> str:
    problems = validate(rows)
    if problems:
        raise ValueError("; ".join(problems))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue()


def check_facts(sources: Iterable[Source], docs_dir: Path) -> List[str]:
    """Every 'facts' string of a FAQ pair must appear in the generated .docx of its own document.

    Keeps the expected answers honest: if someone edits a policy and forgets the test set, this fails.
    """
    problems: List[str] = []
    for s in sources:
        f = Path(docs_dir) / s.library / s.docx_name
        if not f.exists():
            problems.append(f"{s.docx_name}: not built")
            continue
        text = docx_text(f).lower()
        for item in s.faq:
            for fact in item.get("facts", []):
                if str(fact).lower() not in text:
                    problems.append(f"{s.docx_name}: fact '{fact}' (question: {item['q']}) is not in the document")
    return problems


def validate_conversation_csv(text: str) -> List[str]:
    """Validate the conversationNumber,question,response format (Learn: max 20 conversations, 6 questions each)."""
    problems: List[str] = []
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or [h.strip() for h in reader.fieldnames][:2] != ["conversationNumber", "question"]:
        return ["header must start with conversationNumber,question (optional third column: response)"]
    per_conv: dict = {}
    for n, row in enumerate(reader, 2):
        num = (row.get("conversationNumber") or "").strip()
        q = (row.get("question") or "").strip()
        if not num.isdigit():
            problems.append(f"line {n}: conversationNumber must be a whole number")
            continue
        if not q:
            problems.append(f"line {n}: empty question")
        if len(q) > MAX_QUESTION_CHARS:
            problems.append(f"line {n}: question over {MAX_QUESTION_CHARS} characters")
        per_conv[num] = per_conv.get(num, 0) + 1
    if len(per_conv) > 20:
        problems.append(f"{len(per_conv)} conversations; the limit is 20")
    for num, count in per_conv.items():
        if count > 6:
            problems.append(f"conversation {num} has {count} questions; the limit is 6")
    return problems
