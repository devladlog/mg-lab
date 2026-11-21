import json
from pathlib import Path

import pytest

from costwatch import __main__ as cli
from costwatch.estimate import estimate, resources_from_whatif, to_markdown


def test_lab_profile_fixed_cost(prices, whatif):
    est = estimate(resources_from_whatif(whatif("whatif-ep2-lab.json")), prices)
    by_type = {}
    for p in est.priced:
        by_type[p.item.resource_type] = by_type.get(p.item.resource_type, 0) + p.monthly
    assert set(by_type) == {"Microsoft.Web/serverfarms", "Microsoft.Network/privateEndpoints"}
    assert by_type["Microsoft.Network/privateEndpoints"] == pytest.approx(13.10, abs=0.01)   # 2 x 6.55
    assert est.monthly_total == pytest.approx(24.90, abs=0.01)
    # 15 changes in the what-if, 3 priced lines, the rest listed as not estimated (none dropped)
    assert len(est.priced) + len(est.not_estimated) == 15


def test_prod_profile_is_ten_times_the_lab(prices, whatif):
    lab = estimate(resources_from_whatif(whatif("whatif-ep2-lab.json")), prices).monthly_total
    prod = estimate(resources_from_whatif(whatif("whatif-ep2-prod.json")), prices)
    [plan] = [p for p in prod.priced if p.item.resource_type == "Microsoft.Web/serverfarms"]
    assert plan.item.quantity == 2 and "P1v3 x2 (Linux)" in plan.item.description
    assert prod.monthly_total == pytest.approx(246.40, abs=0.01)
    assert prod.monthly_total / lab > 9


def test_rest_shape_modify_counts_after_and_delete_is_not_priced(prices, whatif):
    est = estimate(resources_from_whatif(whatif("whatif-rest-scale-out.json")), prices)
    names = [p.item.resource_id.rsplit("/", 1)[-1] for p in est.priced]
    assert "pe-contoso-lab-vault" not in names                 # being deleted
    [plan] = [p for p in est.priced if p.item.resource_type == "Microsoft.Web/serverfarms"]
    assert plan.item.quantity == 3                              # the scale-out in the "after" state


def test_failed_whatif_is_refused():
    with pytest.raises(ValueError, match="Failed"):
        resources_from_whatif({"status": "Failed", "error": {"code": "InvalidTemplate"}})


def test_markdown_lists_total_budget_and_what_was_not_estimated(prices, whatif):
    md = to_markdown(estimate(resources_from_whatif(whatif("whatif-ep2-prod.json")), prices), budget=25)
    assert "**246.40 EUR**" in md and "Budget 25.00 EUR: **OVER**" in md
    assert "11 x usage-based or not mapped" in md and "730 hours" in md


@pytest.mark.parametrize("fixture, budget, code", [("whatif-ep2-lab.json", 25, 0), ("whatif-ep2-prod.json", 25, 1),
                                                   ("whatif-ep2-prod.json", None, 0)])
def test_cli_exit_codes_gate_the_pipeline(prices, fixture, budget, code, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prices", lambda args: prices)
    src = tmp_path / fixture
    src.write_text((Path(__file__).parent / "fixtures" / fixture).read_text())
    argv = ["estimate", str(src), "--summary", str(tmp_path / "s.md")] + (["--budget", str(budget)] if budget else [])
    assert cli.main(argv) == code
    assert (tmp_path / "s.md").read_text().startswith("## Cost estimate")
    if code == 1:
        assert "##vso[task.logissue type=error]" in capsys.readouterr().err


def test_cli_exit_2_when_a_price_is_missing(tmp_path, monkeypatch, capsys):
    from costwatch.prices import RetailPrices
    empty = RetailPrices(fetch=lambda u: (200, {}, json.dumps({"Items": [], "NextPageLink": None})))
    monkeypatch.setattr(cli, "_prices", lambda args: empty)
    doc = tmp_path / "w.json"
    doc.write_text(json.dumps({"status": "Succeeded", "changes": [{"changeType": "Create", "resourceId": "/x/pe",
        "after": {"id": "/x/pe", "type": "Microsoft.Network/privateEndpoints", "location": "swedencentral"}}]}))
    assert cli.main(["estimate", str(doc), "--budget", "10"]) == 2
    assert "expected exactly 1 price" in capsys.readouterr().err
