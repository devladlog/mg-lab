import pytest

from llmprobe import guards, tokens

DATA = __import__("pathlib").Path(__file__).resolve().parents[1] / "data"


def test_matches_learns_token_counting_example():
    # Learn, "Token counting in AI": "Tell me about the solar system." -> 41551 757 922 279 13238 1887 13 (7 tokens)
    enc = tokens.get_encoding("cl100k_base")
    assert enc.encode("Tell me about the solar system.") == [41551, 757, 922, 279, 13238, 1887, 13]
    assert tokens.count("Tell me about the solar system.", "cl100k_base") == 7


def test_encoding_for_models():
    assert tokens.encoding_name_for("gpt-4.1-mini") == "o200k_base"
    assert tokens.encoding_name_for("gpt-4") == "cl100k_base"
    assert tokens.encoding_name_for("some-unknown-model") == "o200k_base"


def test_pieces_roundtrip():
    text = "Quantos dias de férias tenho?"
    assert "".join(tokens.pieces(text)) == text


def test_pairs_file_is_well_formed():
    pairs = tokens.load_pairs(DATA / "pairs.json")
    assert len(pairs) >= 5 and all(p["pt"] != p["en"] for p in pairs)


def test_load_pairs_rejects_missing_fields(tmp_path):
    f = tmp_path / "p.json"
    f.write_text('[{"id": "x", "en": "a"}]')
    with pytest.raises(ValueError):
        tokens.load_pairs(f)


def test_compare_and_totals_use_the_same_numbers():
    rows = tokens.compare([{"id": "a", "en": "Hello world", "pt": "Olá mundo, tudo bem consigo hoje?"}])
    r = rows[0]
    assert r["o200k_base"]["en"] == tokens.count("Hello world", "o200k_base")
    assert r["o200k_base"]["ratio"] == round(r["o200k_base"]["pt"] / r["o200k_base"]["en"], 2)
    assert tokens.totals(rows)["cl100k_base"]["en"] == r["cl100k_base"]["en"]


def test_newer_encoding_is_not_worse_on_the_sample_and_portuguese_costs_more():
    # a property of the committed sample sentences (measured with tiktoken), not a general claim about languages
    t = tokens.totals(tokens.compare(tokens.load_pairs(DATA / "pairs.json")))
    assert t["o200k_base"]["pt"] <= t["cl100k_base"]["pt"]
    assert t["o200k_base"]["pt"] > t["o200k_base"]["en"]


def test_render_has_a_total_line():
    out = tokens.render(tokens.compare(tokens.load_pairs(DATA / "pairs.json")))
    assert out.splitlines()[-1].startswith("total")


@pytest.mark.parametrize("m", ["o3", "o4-mini", "gpt-5-mini", "GPT-5.1"])
def test_reasoning_models_are_refused(m):
    assert guards.is_reasoning_family(m)
    with pytest.raises(guards.ModelError):
        guards.ensure_sampling_model(m)


@pytest.mark.parametrize("m", ["gpt-4.1-mini", "gpt-4o", "gpt-4.1"])
def test_non_reasoning_models_pass(m):
    guards.ensure_sampling_model(m)


def test_override_for_unverified_models():
    guards.ensure_sampling_model("gpt-5-chat", allow_unverified=True)
