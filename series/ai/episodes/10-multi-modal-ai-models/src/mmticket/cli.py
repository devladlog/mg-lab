"""python -m mmticket samples | voice | transcribe | ticket | evaluate"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import evaluate as ev
from . import guard, samples, speech
from .client import make_client
from .images import ImageError, prepare_image
from .ticket import TicketError, extract
from .transcribe import AudioError, transcribe


def _common(p):
    p.add_argument("--endpoint", default=os.environ.get("MMTICKET_ENDPOINT"), help="https://<name>.openai.azure.com")
    p.add_argument("--vision", default="vision", help="deployment name of the vision model (gpt-4.1-mini)")
    p.add_argument("--whisper", default="whisper", help="deployment name of the Whisper model")
    p.add_argument("--tts", default="tts", help="deployment name of the TTS model")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mmticket")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("samples", help="draw the fictional screenshots (no Azure call)")
    s.add_argument("--out", default="build/images")
    v = sub.add_parser("voice", help="make the fictional voice notes with a TTS deployment")
    _common(v)
    v.add_argument("--out", default="build/audio")
    v.add_argument("--voice", default="alloy")
    t = sub.add_parser("transcribe", help="transcribe one audio file with Whisper")
    _common(t)
    t.add_argument("file")
    t.add_argument("--language", default=None)
    k = sub.add_parser("ticket", help="screenshot (+ voice note) -> ticket")
    _common(k)
    k.add_argument("--image", action="append", required=True)
    k.add_argument("--audio")
    k.add_argument("--language", default=None)
    k.add_argument("--detail", default="high", choices=["low", "high", "auto"])
    e = sub.add_parser("evaluate", help="compare image detail low vs high on all cases; exit 1 if none passes")
    _common(e)
    e.add_argument("--images", default="build/images")
    e.add_argument("--audio-dir", default=None)
    e.add_argument("--min-code-accuracy", type=float, default=0.85)
    return ap


def _client(a):
    if not a.endpoint:
        raise SystemExit("--endpoint or MMTICKET_ENDPOINT is required")
    return make_client(a.endpoint)


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return _run(a)
    except (ImageError, AudioError, TicketError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _run(a) -> int:
    if a.cmd == "samples":
        for p in samples.write_all(a.out):
            print(p)
        return 0
    c = _client(a)
    if a.cmd == "voice":
        for case in samples.load_cases():
            if case.get("voice"):
                p = speech.synthesize(c, a.tts, case["voice"], Path(a.out) / f"{case['id']}.mp3", a.voice)
                print(f"{p}  (synthetic speech)")
        return 0
    if a.cmd == "transcribe":
        print(transcribe(c, a.whisper, a.file, a.language))
        return 0
    if a.cmd == "ticket":
        imgs = [prepare_image(p) for p in a.image]
        for i in imgs:
            print(f"{i.name}: {i.width}x{i.height}, {i.bytes_out} bytes" + (", metadata removed" if i.metadata_removed else ""))
        text = transcribe(c, a.whisper, a.audio, a.language) if a.audio else None
        t, u = extract(c, a.vision, imgs, text, a.detail)
        t = guard.apply(t, text)
        print(t.to_json())
        print(f"usage: prompt_tokens={u.prompt_tokens} completion_tokens={u.completion_tokens}")
        return 0
    cases = {x["id"]: x for x in samples.load_cases()}
    texts = {cid: ev.get_transcript(c, a.whisper, case, a.audio_dir) for cid, case in cases.items()}
    for cid, (_t, src) in texts.items():
        print(f"{cid}: transcript source = {src}")
    summaries = []
    for detail in ("low", "high"):
        rs = [ev.run_case(c, a.vision, case, Path(a.images) / f"{cid}.png", texts[cid][0], detail)
              for cid, case in cases.items()]
        summaries.append(ev.summarise(rs, cases))
    choice, reasons = ev.decide(summaries, min_code=a.min_code_accuracy)
    print(ev.render(summaries, choice, reasons))
    return 0 if choice else 1
