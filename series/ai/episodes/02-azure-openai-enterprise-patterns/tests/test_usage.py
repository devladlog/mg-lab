from aoai_gateway.usage import CONSUMED, REMAINING, Ledger, gateway_headers


def test_gateway_headers_are_case_insensitive_and_ignore_junk():
    h = {"X-Gateway-Remaining-Tokens": "1650", "x-gateway-tokens-consumed": "350", "x-other": "1",
         "x-gateway-remaining-quota-tokens": "n/a"}
    assert gateway_headers(h) == {REMAINING: 1650, CONSUMED: 350}


def test_ledger_totals_per_feature_and_csv():
    ledger = Ledger()
    ledger.record("triage", {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
    ledger.record("triage", {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55})
    ledger.record("summaries", None)
    assert ledger.totals["triage"]["total_tokens"] == 175 and ledger.totals["triage"]["calls"] == 2
    assert ledger.to_csv().splitlines() == [
        "feature,calls,prompt_tokens,completion_tokens,total_tokens",
        "summaries,1,0,0,0",
        "triage,2,150,25,175",
    ]


def test_low_budget_uses_the_last_gateway_header():
    ledger = Ledger()
    assert ledger.low_budget(500) is False
    ledger.record("x", {}, {REMAINING: "400"})
    assert ledger.low_budget(500) is True
