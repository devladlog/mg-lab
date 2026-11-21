import pytest

from mmticket import speech, transcribe as tr
from mmticket.transcribe import AudioError


def test_audio_rules(tmp_path):
    ok = tmp_path / "a.mp3"
    ok.write_bytes(b"x")
    assert tr.check_audio(ok) == ok
    (tmp_path / "a.ogg").write_bytes(b"x")
    (tmp_path / "e.wav").write_bytes(b"")
    for name, msg in (("a.ogg", "not supported"), ("e.wav", "empty")):
        with pytest.raises(AudioError, match=msg):
            tr.check_audio(tmp_path / name)


def test_over_25_mb_points_to_batch_transcription(tmp_path, monkeypatch):
    p = tmp_path / "long.mp3"
    p.write_bytes(b"x" * 10)
    monkeypatch.setattr(tr, "MAX_BYTES", 5)
    with pytest.raises(AudioError, match="25 MB.*batch transcription"):
        tr.check_audio(p)


def test_file_names_are_made_ascii_and_keep_the_extension():
    assert tr.safe_name("reunião do João.mp3") == "reuni_o_do_Jo_o.mp3"
    assert tr.safe_name("çãé.wav") == "audio.wav"
    assert tr.safe_name("ok-1.m4a") == "ok-1.m4a"


def test_transcribe_sends_the_model_ascii_name_language_and_the_entra_token(client, stub, cred, tmp_path):
    f = tmp_path / "nota de voz ç.mp3"
    f.write_bytes(b"ID3audio")
    stub.transcripts["nota_de_voz.mp3"] = " Bom dia. "
    assert tr.transcribe(client, "whisper", f, language="pt", prompt="ID-5501") == "Bom dia."
    r = stub.last("/audio/transcriptions")
    assert r["path"] == "/openai/v1/audio/transcriptions" and r["auth"] == "Bearer fake-entra-token"
    assert r["fields"]["model"][1] == "whisper" and r["fields"]["language"][1] == "pt"
    assert r["fields"]["prompt"][1] == "ID-5501" and r["fields"]["file"] == ("nota_de_voz.mp3", b"ID3audio")
    assert "https://ai.azure.com/.default" in cred.scopes


def test_speech_writes_the_bytes_and_enforces_the_4096_character_limit(client, stub, tmp_path):
    out = speech.synthesize(client, "tts", "The code is CX-4102.", tmp_path / "x" / "n.mp3", voice="alloy")
    assert out.read_bytes() == b"ID3FAKE-MP3-BYTES"
    assert stub.last("/audio/speech")["json"] == {"model": "tts", "voice": "alloy", "input": "The code is CX-4102.",
                                                  "response_format": "mp3"}
    with pytest.raises(ValueError, match="4096"):
        speech.synthesize(client, "tts", "a" * 4097, tmp_path / "y.mp3")
    with pytest.raises(ValueError, match="nothing to say"):
        speech.synthesize(client, "tts", "  ", tmp_path / "y.mp3")
    with pytest.raises(ValueError, match="format"):
        speech.synthesize(client, "tts", "hi", tmp_path / "y.ogg", fmt="ogg")
