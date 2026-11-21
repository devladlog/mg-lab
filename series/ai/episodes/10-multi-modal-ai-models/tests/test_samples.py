import json

from mmticket import samples
from mmticket.images import prepare_image
from mmticket.ticket import QUEUES, SEVERITIES


def test_cases_are_well_formed_and_cover_the_hard_situations(cases):
    kinds = {c["kind"] for c in cases.values()}
    assert {"clean", "small_text", "dark_mode", "portuguese", "prompt_injection", "conflict", "no_code"} <= kinds
    for c in cases.values():
        t = c["truth"]
        assert t["queue"] in QUEUES and t["severity"] in SEVERITIES and isinstance(t["needs_human"], bool)
        assert c["voice"] is None or len(c["voice"]) < 4096
    assert cases["sync-injection"]["must_not"] and cases["sync-injection"]["hidden_text"]
    assert cases["vpn-conflict"]["truth"]["needs_human"] and "CX-4120" in cases["vpn-conflict"]["voice"]
    assert "CX-4120" not in " ".join(cases["vpn-conflict"]["lines"])


def test_all_pictures_render_and_are_accepted_by_the_image_rules(image_dir, cases):
    files = sorted(p.name for p in image_dir.glob("*.png"))
    assert files == sorted(f"{cid}.png" for cid in cases)
    for cid in cases:
        p = prepare_image(image_dir / f"{cid}.png")
        assert p.bytes_out < 2_000_000 and p.width >= 1000


def test_rendering_is_deterministic_and_the_cases_differ(image_dir, tmp_path):
    again = samples.write_all(tmp_path)
    assert (tmp_path / "vpn-clean.png").read_bytes() == (image_dir / "vpn-clean.png").read_bytes()
    assert (image_dir / "vpn-clean.png").read_bytes() != (image_dir / "print-dark.png").read_bytes()
    assert len(again) == 7


def test_the_injection_text_is_only_in_the_one_case():
    raw = json.loads(samples.DATA.read_text(encoding="utf-8"))
    assert [c["id"] for c in raw if c.get("hidden_text")] == ["sync-injection"]
    assert any("ç" in line or "ã" in line for c in raw for line in c["lines"])      # real Portuguese diacritics, not escapes
