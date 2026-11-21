import pytest

from hrrag.chunking import chunk_folder
from hrrag.evaluate import load_questions, score_mode
from hrrag.fusion import RRF_K, rrf
from hrrag.local import HashingEmbedder, LocalIndex


def test_rrf_uses_one_over_rank_plus_60():
    fused = dict(rrf([["a", "b"]]))
    assert fused["a"] == pytest.approx(1 / (1 + RRF_K))
    assert fused["b"] == pytest.approx(1 / (2 + RRF_K))


def test_document_good_in_both_lists_beats_first_in_one():
    keyword = ["exp-4", "meals", "mileage"]
    vector = ["flights", "meals", "carry-over"]
    fused = rrf([keyword, vector])
    assert fused[0][0] == "meals"  # rank 2 + rank 2 beats rank 1 + absent


def test_rrf_weights_change_the_balance():
    keyword, vector = ["k1", "shared"], ["v1", "shared"]
    assert rrf([keyword, vector], weights=[1.0, 3.0])[0][0] in ("v1", "shared")
    assert rrf([keyword, vector], weights=[1.0, 3.0])[0][0] != "k1"
    with pytest.raises(ValueError):
        rrf([keyword, vector], weights=[1.0])


def test_hashing_embedder_is_deterministic_and_unit_length():
    e = HashingEmbedder(64)
    a, b = e.embed(["annual leave"]), e.embed(["annual leave"])
    assert a == b and sum(x * x for x in a[0]) == pytest.approx(1.0)


@pytest.fixture(scope="module")
def local_index():
    from pathlib import Path

    return LocalIndex(chunk_folder(Path(__file__).resolve().parents[1] / "data" / "handbook"))


def test_keyword_search_nails_exact_codes(local_index):
    assert local_index.search("What is form HR-31 for?", "keyword", 1)[0].section_key == "remote-work#working-from-abroad"
    assert local_index.search("What does policy EXP-4 cover?", "keyword", 1)[0].section_key == "expenses#client-entertainment"


def test_retrieval_always_returns_something_even_out_of_scope(local_index):
    # Retrieval has no notion of "no answer": the answer step must refuse, not the search.
    assert len(local_index.search("What is the company car policy?", "hybrid", 5)) == 5


def test_harness_scores_every_mode_on_the_handbook(local_index, questions_path):
    questions = load_questions(questions_path)
    for mode in ("keyword", "vector", "hybrid"):
        s = score_mode(lambda q, m, k: local_index.search(q, m, k), questions, mode)
        assert s.n == 16 and 0 <= s.hit1 <= s.hitk <= 1 and 0 <= s.mrr <= 1
