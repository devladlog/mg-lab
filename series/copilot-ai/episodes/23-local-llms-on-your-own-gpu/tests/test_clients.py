import pytest

from local_llm import openai_compat
from local_llm.http import LlmHttpError, assert_local, is_local_url
from local_llm.ollama import ChatResult, OllamaClient, placement


def test_chat_parses_timings_into_tokens_per_second(server):
    r = OllamaClient(server.url).chat("demo-8b:q4", [{"role": "user", "content": "hi"}], options={"seed": 1}, keep_alive="5m", think=False)
    assert r.gen_tokens == 100 and r.gen_tps == pytest.approx(100.0)
    assert r.prompt_tps == pytest.approx(500.0) and r.load_s == pytest.approx(1.5) and r.total_s == pytest.approx(2.5)
    body = server.requests[-1][2]
    assert body["stream"] is False and body["keep_alive"] == "5m" and body["think"] is False and body["options"] == {"seed": 1}


def test_optional_fields_are_not_sent_when_unset(server):
    OllamaClient(server.url).chat("demo-8b:q4", [{"role": "user", "content": "hi"}])
    assert set(server.requests[-1][2]) == {"model", "messages", "stream"}


def test_tags_ps_show_unload(server):
    c = OllamaClient(server.url)
    assert [m["name"] for m in c.tags()] == ["demo-8b:q4", "demo-70b:q4"]
    assert c.ps()[0]["size_vram"] > 0
    assert c.show("demo-8b:q4")["model_info"]["general.architecture"] == "llama"
    c.unload("demo-8b:q4")
    assert server.requests[-1][2] == {"model": "demo-8b:q4", "messages": [], "keep_alive": 0}


def test_http_error_is_raised_with_status(server):
    with pytest.raises(LlmHttpError) as e:
        OllamaClient(server.url)._call("GET", "/nope")
    assert e.value.status == 404


def test_connection_refused_is_a_clear_error():
    with pytest.raises(ConnectionError, match="cannot reach"):
        OllamaClient("http://127.0.0.1:9", timeout=2).tags()


def test_placement_labels():
    assert placement({"size": 10, "size_vram": 10}) == "100% GPU"
    assert placement({"size": 10, "size_vram": 0}) == "100% CPU"
    assert placement({"size": 100, "size_vram": 75}) == "25%/75% CPU/GPU"
    assert placement({}) == "unknown"


def test_openai_compat_chat_and_models(server):
    c = openai_compat.OpenAICompatClient(server.url + "/v1")
    assert c.models() == ["demo-8b:q4"]
    r = c.chat("demo-8b:q4", [{"role": "user", "content": "hi"}], max_tokens=5, temperature=0, seed=3)
    assert (r.text, r.prompt_tokens, r.gen_tokens) == ("hi", 7, 3)
    assert server.requests[-1][2]["max_tokens"] == 5 and server.requests[-1][2]["seed"] == 3
    assert isinstance(r, ChatResult)


def test_probe_reports_up_and_down(server):
    res = openai_compat.probe({"fake": server.url + "/v1", "dead": "http://127.0.0.1:9/v1"}, timeout=2)
    assert res["fake"]["up"] and res["fake"]["models"] == ["demo-8b:q4"]
    assert not res["dead"]["up"] and res["dead"]["error"]


def test_known_servers_use_documented_ports():
    assert openai_compat.KNOWN_SERVERS["ollama"].endswith(":11434/v1")
    assert openai_compat.KNOWN_SERVERS["lmstudio"].endswith(":1234/v1")


@pytest.mark.parametrize("url,ok", [("http://127.0.0.1:11434", True), ("http://localhost:1234/v1", True),
                                    ("http://10.50.0.1:11434", True), ("https://api.openai.com/v1", False),
                                    ("http://8.8.8.8", False), ("http://my-server.example.com", False)])
def test_is_local_url(url, ok):
    assert is_local_url(url) is ok


def test_assert_local_refuses_remote():
    with pytest.raises(ValueError, match="non-local"):
        assert_local("https://api.example.com")
