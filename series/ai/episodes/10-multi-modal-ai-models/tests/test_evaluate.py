import pytest

from conftest import oracle
from mmticket import evaluate as ev


def run_all(client, stub, image_dir, cases, detail, audio_dir=None):
    out = []
    for cid, c in cases.items():
        text, _ = ev.get_transcript(client, None, c, None)
        out.append(ev.run_case(client, "vision", c, image_dir / f"{cid}.png", text, detail))
    return ev.summarise(out, cases), out


def both(client, stub, image_dir, cases, **kw):
    return [run_all(client, stub, image_dir, cases, d)[0] for d in ("low", "high")]


def test_a_perfect_model_passes_and_the_cheaper_detail_wins(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases)
    s = both(client, stub, image_dir, cases)
    assert all(x.code_acc == 1 and x.queue_acc == 1 and x.human_recall == 1 and x.injections == 0 for x in s)
    choice, reasons = ev.decide(s)
    assert choice == "low" and not any(reasons.values())
    assert s[0].avg_prompt_tokens == 125 and s[1].avg_prompt_tokens == 805     # the stub's made-up usage, measured not computed


def test_low_detail_that_cannot_read_small_text_is_rejected_and_high_is_chosen(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases, small_text_fails_at_low=True)
    s = both(client, stub, image_dir, cases, )
    low, high = s
    assert low.code_acc == pytest.approx(6 / 7) and high.code_acc == 1
    choice, reasons = ev.decide(s, min_code=0.95)
    assert choice == "high" and any("error-code accuracy" in w for w in reasons["low"])


def test_following_an_instruction_hidden_in_the_image_fails_the_gate(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases, follow_injection=True)
    s = both(client, stub, image_dir, cases)
    assert all(x.injections == 1 for x in s)
    choice, reasons = ev.decide(s)
    assert choice is None and "followed an instruction written inside the image" in " ".join(reasons["high"])


def test_a_conflict_the_model_missed_is_still_caught_by_the_guard(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases, silent=True)      # the model itself never sets needs_human
    _, results = run_all(client, stub, image_dir, cases, "high")
    r = {x.case_id: x for x in results}
    assert r["vpn-conflict"].human_ok and any(f.startswith("conflict") for f in r["vpn-conflict"].flags)
    assert r["sync-injection"].human_ok and any("injection" in f for f in r["sync-injection"].flags)
    assert r["print-nocode"].human_ok and r["print-nocode"].flags == ["no error code could be read"]


def test_failed_calls_and_bad_json_count_as_wrong(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases, bad_json=("vpn-clean",))
    s, results = run_all(client, stub, image_dir, cases, "high")
    assert s.errors == 1 and s.code_acc == pytest.approx(6 / 7)
    assert "1 call(s) failed" in ev.gates(s)
    stub.chat_fail = True
    s, _ = run_all(client, stub, image_dir, cases, "low")
    assert s.errors == 7 and s.code_acc == 0 and s.avg_prompt_tokens == 0


def test_transcripts_come_from_whisper_when_audio_exists_else_from_the_reference_text(client, stub, cases, tmp_path):
    c = cases["vpn-clean"]
    assert ev.get_transcript(client, "whisper", cases["print-dark"], tmp_path) == (None, "none")
    assert ev.get_transcript(client, "whisper", c, tmp_path) == (c["voice"], "reference text")
    (tmp_path / "vpn-clean.mp3").write_bytes(b"ID3x")
    stub.transcripts["vpn-clean.mp3"] = "spoken words CX-4102"
    assert ev.get_transcript(client, "whisper", c, tmp_path) == ("spoken words CX-4102", "whisper")
    assert ev.get_transcript(client, "whisper", cases["access-pt"], tmp_path)[1] == "reference text"


def test_render_states_the_decision(client, stub, image_dir, cases, by_image):
    stub.chat = oracle(by_image, cases)
    s = both(client, stub, image_dir, cases)
    text = ev.render(s, *ev.decide(s))
    assert "RESULT: use detail=low" in text and "prompt tok/case" in text
    stub.chat = oracle(by_image, cases, follow_injection=True)
    s = both(client, stub, image_dir, cases)
    assert "do not ship" in ev.render(s, *ev.decide(s))
