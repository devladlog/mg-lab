import re

import pytest

from hrrag.chunking import chunk_folder, chunk_markdown, split_long
from hrrag.evaluate import load_questions

DOC = """# Leave policy

<!-- boilerplate that must never be indexed -->

## Annual leave

25 days per year.

## Carry-over

Up to 5 days until 31 March.
"""


def test_one_chunk_per_section_with_title_path_and_no_boilerplate():
    chunks = chunk_markdown(DOC, "leave")
    assert [c.section for c in chunks] == ["Annual leave", "Carry-over"]
    assert chunks[1].content.startswith("Leave policy > Carry-over\n\n")
    assert chunks[1].section_key == "leave#carry-over"
    assert all("boilerplate" not in c.content for c in chunks)


def test_long_section_is_split_with_overlap_and_within_budget():
    sentences = [f"Rule number {i} says employees must follow procedure {i} carefully." for i in range(80)]
    pieces = split_long(" ".join(sentences), max_chars=600, overlap=150)
    assert len(pieces) > 3
    assert all(len(p) <= 600 for p in pieces)
    for prev, nxt in zip(pieces, pieces[1:]):
        assert nxt.split(" ", 3)[2] in prev  # the next piece starts with text repeated from the previous one
        assert not nxt[0].islower() or nxt.split(" ")[0] in prev  # never starts mid-word


def test_overlap_must_be_less_than_half_the_chunk():
    with pytest.raises(ValueError):
        split_long("x " * 2000, max_chars=1000, overlap=500)


def test_handbook_chunk_ids_are_unique_valid_search_keys(handbook):
    chunks = chunk_folder(handbook)
    assert len(chunks) == 25
    assert all(re.fullmatch(r"[A-Za-z0-9_\-=]+", c.id) for c in chunks)
    assert all(len(c.content) <= 2000 for c in chunks)


def test_every_labelled_section_exists_in_the_handbook(handbook, questions_path):
    keys = {c.section_key for c in chunk_folder(handbook)}
    for q in load_questions(questions_path):
        assert set(q["expected"]) <= keys, q["id"]
