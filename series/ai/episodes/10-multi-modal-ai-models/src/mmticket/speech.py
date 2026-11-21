"""Text to speech: used only to make the fictional voice notes for the demo (a TTS deployment, `tts` or `tts-hd`).
Learn: input is at most 4096 characters. The output is synthetic speech, so say so wherever it is used."""
from __future__ import annotations

from pathlib import Path

MAX_CHARS = 4096
FORMATS = ("mp3", "wav", "opus", "aac", "flac")


def synthesize(client, deployment: str, text: str, out: str | Path, voice: str = "alloy", fmt: str = "mp3") -> Path:
    if not text.strip():
        raise ValueError("nothing to say")
    if len(text) > MAX_CHARS:
        raise ValueError(f"{len(text)} characters; text to speech takes at most {MAX_CHARS}")
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    resp = client.audio.speech.create(model=deployment, voice=voice, input=text, response_format=fmt)
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(resp.content)
    return p
