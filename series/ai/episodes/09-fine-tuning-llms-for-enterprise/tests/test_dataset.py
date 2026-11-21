from collections import Counter

from fttriage import dataset, validate
from fttriage.labels import CATEGORIES, parse_label
from fttriage.prompts import FEW_SHOT, SHORT_SYSTEM, baseline_system


def test_labelled_data_shape(data):
    ex, golden, _ = data
    assert len(ex) == 150 and len({e.id for e in ex}) == 150
    assert set(e.category for e in ex) == set(CATEGORIES)
    assert all(e.label is not None for e in ex)
    assert len(golden) == 16 and all(e.label is None for e in golden)      # episode 8's golden set: category only
    langs = Counter(e.lang for e in ex)
    assert langs["en"] > 60 and langs["pt"] > 40                             # both languages are really there


def test_split_is_stratified_disjoint_and_deterministic(data):
    ex, _, sp = data
    assert (len(sp.train), len(sp.validation), len(sp.test)) == (100, 21, 29)
    ids = [e.id for e in sp.train + sp.validation + sp.test]
    assert len(ids) == len(set(ids)) == 150
    for part in (sp.train, sp.test):
        assert set(e.category for e in part) == set(CATEGORIES)
    again = dataset.split(ex)
    assert [e.id for e in again.test] == [e.id for e in sp.test]
    other = dataset.split(ex, seed=99)
    assert [e.id for e in other.test] != [e.id for e in sp.test]


def test_no_leakage_between_train_and_held_out_data(data):
    """The point of the split: nothing the model trains on is also something we grade it on."""
    _, golden, sp = data
    rows = [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.train]
    held = {"validation": [e.text for e in sp.validation], "test": [e.text for e in sp.test],
            "episode 8 golden": [e.text for e in golden]}
    rep = validate.check_leakage(rows, held)
    assert rep.ok, [i.message for i in rep.errors]


def test_baseline_prompt_examples_are_not_in_the_test_data(data):
    """The long prompt must not be graded on questions it was shown."""
    _, golden, sp = data
    test_texts = [e.text for e in sp.test + golden]
    for text, *_ in FEW_SHOT:
        assert all(validate.jaccard(text, t) < validate.NEAR_DUPLICATE for t in test_texts), text


def test_chat_rows_and_answer_format(data):
    _, _, sp = data
    row = dataset.to_chat(sp.train[0], SHORT_SYSTEM)
    assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]
    lab = parse_label(row["messages"][2]["content"])
    assert lab == sp.train[0].label
    assert row["messages"][2]["content"].startswith('{"category":')        # compact, fixed key order


def test_golden_cannot_become_a_training_example(data):
    _, golden, _ = data
    try:
        dataset.to_chat(golden[0], SHORT_SYSTEM)
    except ValueError as e:
        assert "no full label" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_jsonl_roundtrip_with_bom_and_diacritics(tmp_path, data):
    _, _, sp = data
    pt = next(e for e in sp.train if e.lang == "pt" and any(c in e.text for c in "ãçéíóú"))
    p = tmp_path / "t.jsonl"
    dataset.write_jsonl(p, [dataset.to_chat(pt, SHORT_SYSTEM)])
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and pt.text.encode("utf-8") in raw          # BOM, and real UTF-8 not \u escapes
    assert dataset.read_jsonl(p)[0]["messages"][1]["content"] == pt.text
    dataset.write_jsonl(p, [dataset.to_chat(pt, SHORT_SYSTEM)], bom=False)
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")


def test_long_prompt_is_much_longer_than_the_short_one():
    from fttriage import tokens
    assert tokens.count_text(baseline_system()) > 10 * tokens.count_text(SHORT_SYSTEM)


def test_the_repo_dataset_passes_every_preflight_check(data, tmp_path):
    _, golden, sp = data
    train = [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.train]
    val = [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.validation]
    assert validate.check_rows(train, "training").ok and validate.check_rows(val, "validation").ok
    assert not validate.check_rows(train, "training").warnings      # >= 50 examples, every class has >= 5
