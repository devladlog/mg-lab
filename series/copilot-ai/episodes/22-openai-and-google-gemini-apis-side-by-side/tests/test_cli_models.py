import json

import pytest

from llm_sidebyside import cli, contract
from llm_sidebyside.errors import Failure, classify, with_retry
from llm_sidebyside.models import Outcome, Usage, estimate_cost_usd, load_prices
from conftest import SAMPLES
import os


def test_cost_estimate_matches_hand_arithmetic():
    prices = load_prices(os.path.join(SAMPLES, "prices.json"))
    o = Outcome("openai", "gpt-6.2-sol", "complete", usage=Usage(1_000_000, 100_000, 40_000, 200_000))
    # 800k fresh * 2 + 200k cached * 0.1 + 100k output (reasoning already inside) * 10 = 1.6 + 0.02 + 1.0
    assert estimate_cost_usd(o, prices) == pytest.approx(2.62)
    g = Outcome("gemini", "gemini-3.8-flash", "complete", usage=Usage(1_000_000, 100_000, 40_000, 0))
    # 1M * 0.75 + (100k + 40k thinking) * 3.75
    assert estimate_cost_usd(g, prices) == pytest.approx(0.75 + 0.525)
    assert estimate_cost_usd(Outcome("openai", "unknown", "complete"), prices) is None


def test_prices_file_is_dated_and_sourced():
    prices = load_prices(os.path.join(SAMPLES, "prices.json"))
    assert prices["checked"] == "2026-11-21"
    assert all("source" in m for m in prices["models"].values())


def test_with_retry_backs_off_exponentially_and_stops_on_non_retryable():
    slept, calls = [], []

    def flaky():
        calls.append(1)
        raise Failure("x", "server", "boom", 503)
    with pytest.raises(Failure):
        with_retry(flaky, attempts=3, base_delay=1, sleep=slept.append)
    assert slept == [1, 2] and len(calls) == 3
    calls.clear()

    def bad():
        calls.append(1)
        raise Failure("x", "bad_request", "no", 400)
    with pytest.raises(Failure):
        with_retry(bad, sleep=slept.append)
    assert len(calls) == 1


def test_classify_connection_problem_has_no_status():
    f = classify("openai", ConnectionError("reset"))
    assert f.kind == "network" and f.retryable


def test_payloads_command_prints_both_dialects(capsys):
    assert cli.main(["payloads", "extract"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["openai"]["text"]["format"]["strict"] is True
    assert printed["gemini"]["response_format"]["mime_type"] == "application/json"


def test_payloads_never_contain_a_key(capsys):
    cli.main(["payloads"])
    assert "sk-" not in capsys.readouterr().out


def test_schema_command_reports_conversion(capsys):
    assert cli.main(["schema"]) == 0
    out = capsys.readouterr().out
    assert "vendors[].notice_days" in out and "uniqueItems" in out


def test_run_without_keys_exits_2(monkeypatch, capsys):
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert cli.main(["run", "truncate", "--vendor", "openai"]) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err
    assert cli.main(["run", "truncate", "--vendor", "gemini"]) == 2


def test_truncate_prompt_uses_documented_minimum():
    assert contract.TRUNCATE_MAX_TOKENS == 16
