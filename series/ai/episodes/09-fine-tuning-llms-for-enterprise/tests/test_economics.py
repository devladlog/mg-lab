import pytest

from fttriage import economics as eco


def test_training_cost_is_tokens_times_epochs_times_price():
    # Learn's worked example: 1M tokens, two epochs = 2 x the per-million rate
    assert eco.training_cost(1_000_000, 2, 5.0) == pytest.approx(10.0)
    assert eco.training_cost(7_149, 3, 10.0) == pytest.approx(0.21447)


def test_serving_cost_per_call_and_month():
    s = eco.Serving(prompt_tokens=700, completion_tokens=20, input_per_million=2.0, output_per_million=8.0,
                    hosting_per_hour=1.5)
    assert s.per_call() == pytest.approx((700 * 2 + 20 * 8) / 1e6)
    assert s.monthly(1000) == pytest.approx(1000 * s.per_call() + 1.5 * 730)


def test_breakeven_counts_hosting_and_training():
    base = eco.Serving(700, 20, 1.0, 4.0)
    tuned = eco.Serving(40, 20, 1.0, 4.0, hosting_per_hour=0.5)
    saving = base.per_call() - tuned.per_call()
    n = eco.breakeven_calls_per_month(base, tuned, training=120.0, amortise_months=12)
    assert n == pytest.approx((0.5 * 730 + 10.0) / saving)
    assert tuned.monthly(n) + 10.0 == pytest.approx(base.monthly(n))


def test_no_breakeven_when_the_tuned_model_is_not_cheaper_per_call():
    base = eco.Serving(100, 20, 1.0, 4.0)
    dearer = eco.Serving(100, 20, 3.0, 12.0)
    assert eco.breakeven_calls_per_month(base, dearer, 0.0) is None


def test_developer_deployments_have_no_hosting_term():
    base = eco.Serving(700, 20, 1.0, 4.0)
    tuned = eco.Serving(40, 20, 1.0, 4.0, hosting_per_hour=0.0)
    assert eco.breakeven_calls_per_month(base, tuned, 0.0) == 0.0
