import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copilot_landscape import catalog as cat  # noqa: E402


def data():
    return cat.load_catalog()


def test_catalog_file_is_valid():
    assert cat.validate(data()) == []


def test_has_every_family_the_episode_talks_about():
    ids = {e["id"] for e in data()["entries"]}
    for needed in {
        "copilot-chat-basic", "m365-copilot-premium", "copilot-studio", "security-copilot",
        "azure-copilot", "github-copilot", "copilot-fabric-power-bi", "ssms-copilot",
    }:
        assert needed in ids


def test_free_filter_keeps_only_included_entries():
    free = cat.entries(data(), free_only=True)
    assert {e["id"] for e in free} >= {"copilot-chat-basic", "azure-copilot"}
    assert all(e["licence_model"] in {"included", "free-tier"} for e in free)
    assert "m365-copilot-premium" not in {e["id"] for e in free}


def test_area_filter():
    assert {e["id"] for e in cat.entries(data(), area="azure")} == {"azure-copilot"}


def test_price_without_source_is_rejected():
    bad = copy.deepcopy(data())
    bad["entries"][0]["price_source"] = None
    assert any("price needs a price_source" in p for p in cat.validate(bad))


def test_non_official_source_is_rejected():
    bad = copy.deepcopy(data())
    bad["entries"][1]["sources"].append("https://example.com/copilot-pricing")
    assert any("not an official https URL" in p for p in cat.validate(bad))


def test_unknown_vocabulary_is_rejected():
    bad = copy.deepcopy(data())
    bad["entries"][2]["lab_status"] = "probably"
    bad["entries"][3]["licence_model"] = "free-ish"
    problems = cat.validate(bad)
    assert any("lab_status" in p for p in problems)
    assert any("licence_model" in p for p in problems)


def test_duplicate_id_is_rejected():
    bad = copy.deepcopy(data())
    bad["entries"].append(copy.deepcopy(bad["entries"][0]))
    assert any("duplicate id" in p for p in cat.validate(bad))


def test_markdown_has_one_row_per_entry():
    items = cat.entries(data())
    table = cat.to_markdown(items).splitlines()
    assert len(table) == len(items) + 2


def test_no_tenant_identifiers_in_catalog():
    text = (Path(cat.DEFAULT_PATH)).read_text(encoding="utf-8").lower()
    for forbidden in ("onmicrosoft.com", "sharepoint.com", "crm4.dynamics.com", "devladlog.onmicrosoft"):
        assert forbidden not in text
