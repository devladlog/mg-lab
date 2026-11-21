"""Speech to text with a Whisper deployment. Learn: mp3, mp4, mpeg, mpga, m4a, wav, webm; 25 MB per file; ASCII-only
file names. Longer recordings need Azure Speech batch transcription, which this module does not pretend to replace."""
from __future__ import annotations

import re
from pathlib import Path

ALLOWED = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
MAX_BYTES = 25 * 1024 * 1024


class AudioError(ValueError):
    pass


def check_audio(path: str | Path) -> Path:
    p = Path(path)
    if p.suffix.lower() not in ALLOWED:
        raise AudioError(f"{p.name}: {p.suffix or 'no extension'} is not supported; use one of {sorted(ALLOWED)}")
    size = p.stat().st_size
    if size == 0:
        raise AudioError(f"{p.name}: the file is empty")
    if size > MAX_BYTES:
        raise AudioError(f"{p.name}: {size / 1_048_576:.1f} MB is over the 25 MB limit; split it or use Azure Speech "
                         f"batch transcription")
    return p


def safe_name(name: str) -> str:
    """Learn: file names must be ASCII. Keep the extension, replace anything else."""
    stem, dot, ext = name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "audio"
    return f"{stem}{dot}{ext}"


def transcribe(client, deployment: str, path: str | Path, language: str | None = None, prompt: str | None = None) -> str:
    p = check_audio(path)
    kwargs = {"model": deployment, "file": (safe_name(p.name), p.read_bytes()), "response_format": "json"}
    if language:
        kwargs["language"] = language       # ISO-639-1 such as "pt": removes the language guess
    if prompt:
        kwargs["prompt"] = prompt           # product names and error codes the speaker may say
    return client.audio.transcriptions.create(**kwargs).text.strip()
