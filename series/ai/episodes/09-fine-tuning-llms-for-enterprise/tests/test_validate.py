import json

from fttriage import dataset, validate
from fttriage.prompts import SHORT_SYSTEM


def row(text="Where can I find the org chart?", answer=None, system=SHORT_SYSTEM):
    answer = answer or '{"category":"other","urgency":"low","needs_human":false}'
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": text},
                         {"role": "assistant", "content": answer}]}


def rows(n):
    return [row(f"Distinct question number {i} about leave policy details") for i in range(n)]


def codes(rep):
    return {i.code for i in rep.issues}


def test_fewer_than_ten_is_an_error_and_under_fifty_a_warning():
    assert "too-few" in codes(validate.check_rows(rows(9)))
    rep = validate.check_rows(rows(20))
    assert "too-few" not in codes(rep) and "few" in codes(rep)
    assert "few" not in codes(validate.check_rows(rows(20), "validation"))


def test_structure_errors():
    bad = rows(12)
    bad[0] = {"messages": [{"role": "user", "content": "hi"}]}
    bad[1] = {"nope": 1}
    bad[2]["messages"][2]["content"] = "payroll"
    bad[3]["messages"][2]["content"] = '{"category":"salary","urgency":"low","needs_human":false}'
    bad[4]["messages"][1]["content"] = "   "
    rep = validate.check_rows(bad)
    assert {"bad-roles", "no-messages", "bad-answer", "empty-content"} <= codes(rep)
    assert len([i for i in rep.errors if i.code == "bad-answer"]) == 2


def test_the_system_message_must_be_the_same_everywhere():
    r = rows(12)
    r[5]["messages"][0]["content"] = "A different system message."
    assert "system-mismatch" in codes(validate.check_rows(r))


def test_duplicates_warn_and_conflicting_labels_block():
    r = rows(12)
    r[1] = dict(r[0])
    assert "duplicate" in codes(validate.check_rows(r))
    r[2] = row(r[0]["messages"][1]["content"], '{"category":"leave","urgency":"low","needs_human":false}')
    assert "conflicting-labels" in codes(validate.check_rows(r))


def test_personal_data_blocks_the_upload():
    samples = {"email": "Please write to ana.silva@contoso.example about it",
               "iban": "My IBAN is PT50 0002 0123 1234 5678 9015 4 please update it",
               "phone": "Call me on 912 345 678 tomorrow",
               "nif_or_long_number": "My tax number is 123456789",
               "card_number": "The card 4111 1111 1111 1111 was charged"}
    for kind, text in samples.items():
        r = rows(12)
        r[3] = row(text)
        rep = validate.check_rows(r)
        assert any(i.code == "pii" and kind in i.message for i in rep.errors), kind


def test_clean_text_with_numbers_is_not_flagged_as_personal_data():
    r = rows(12)
    r[3] = row("Is the office open on the 25th of April and can I get 2 days off in week 17?")
    assert "pii" not in codes(validate.check_rows(r))


def test_leakage_exact_and_near_copies_are_blocked():
    train = [row("How many sick days am I entitled to before I need a medical certificate?")]
    held = {"test": ["how many sick days am I entitled to before I need a medical certificate"]}
    assert "leak-exact" in codes(validate.check_leakage(train, held))
    held = {"golden": ["How many sick days am I entitled to before I need a doctor certificate?"]}
    assert "leak-near" in codes(validate.check_leakage(train, held))
    held = {"golden": ["Where do I park my bicycle at the Porto office?"]}
    assert validate.check_leakage(train, held).ok


def test_too_long_example_is_an_error():
    r = rows(12)
    r[0] = row("word " * 70_000)
    assert "too-long" in codes(validate.check_rows(r))


def test_thin_and_missing_classes_warn():
    rep = validate.check_rows(rows(60))
    msgs = " ".join(i.message for i in rep.warnings if i.code == "thin-class")
    assert "no examples of category 'payroll'" in msgs


def test_file_encoding_checks(tmp_path):
    p = tmp_path / "a.jsonl"
    dataset.write_jsonl(p, rows(3))
    assert validate.check_file_encoding(p).ok and not validate.check_file_encoding(p).warnings
    dataset.write_jsonl(p, rows(3), bom=False)
    assert "no-bom" in codes(validate.check_file_encoding(p))
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(row()).encode() + b"\n{broken\n")
    assert "bad-json" in codes(validate.check_file_encoding(p))
    p.write_bytes(b"\xef\xbb\xbf" + "ordenado já".encode("latin-1") + b"\n")
    assert "not-utf8" in codes(validate.check_file_encoding(p))
