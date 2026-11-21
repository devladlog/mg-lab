import inventory

GROUPS = {"value": [{"id": "g1", "name": "Contoso Sales (Lab)"}, {"id": "g2", "name": "Archive"}]}
DATASETS = {
    "g1": {"value": [{"id": "d1", "name": "TillEventsLegacy", "addRowsAPIEnabled": True, "configuredBy": "alex.demo@contoso.example", "createdDate": "2026-11-24T10:00:00Z"},
                     {"id": "d2", "name": "Contoso Sales", "addRowsAPIEnabled": False},
                     {"id": "d3", "name": "Sensors (streaming)", "ContentProviderType": "RealTimeInStreamingMode"}]},
    "g2": {"value": [{"id": "d4", "name": "Feed", "ContentProviderType": "RealTimeInPubNubMode"}, {"id": "d5", "name": "Read only"}]},
}


def fake_get(path):
    if path == "/v1.0/myorg/groups":
        return GROUPS
    return DATASETS[path.split("/")[4]]


def test_classify():
    assert inventory.classify({"addRowsAPIEnabled": True}) == "push"
    assert inventory.classify({"addRowsAPIEnabled": False}) is None
    assert inventory.classify({"ContentProviderType": "RealTimeInPushMode"}) == "push"
    assert inventory.classify({"ContentProviderType": "RealTimeInStreamingMode"}) == "streaming"
    assert inventory.classify({"ContentProviderType": "RealTimeInPubNubMode"}) == "pubnub"
    assert inventory.classify({"ContentProviderType": "PbixInImportMode"}) is None
    assert inventory.classify({"id": "x", "name": "read-only caller sees only these two"}) is None


def test_finds_only_realtime_models_and_sorts_them():
    rows = inventory.find_realtime_models(fake_get)
    assert [(r["workspace"], r["dataset"], r["kind"]) for r in rows] == [
        ("Archive", "Feed", "pubnub"), ("Contoso Sales (Lab)", "Sensors (streaming)", "streaming"), ("Contoso Sales (Lab)", "TillEventsLegacy", "push")]


def test_csv_has_a_header_and_one_line_per_model():
    out = inventory.to_csv(inventory.find_realtime_models(fake_get)).splitlines()
    assert out[0] == ",".join(inventory.COLUMNS)
    assert len(out) == 4 and out[-1].startswith("Contoso Sales (Lab),g1,TillEventsLegacy,d1,")


def test_no_workspaces_gives_header_only():
    assert inventory.to_csv(inventory.find_realtime_models(lambda p: {"value": []})) == ",".join(inventory.COLUMNS) + "\n"
