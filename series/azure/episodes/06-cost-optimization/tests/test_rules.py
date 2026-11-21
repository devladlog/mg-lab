import pytest

from costwatch.rules import NotEstimated, app_service_sku, price_rules, resource_type, standard_hdd_tier


@pytest.mark.parametrize("sku, expected", [("B1", ("B1", "Basic")), ("S1", ("S1", "Standard")),
                                           ("P1v3", ("P1 v3", "Premium v3")), ("p2v3", ("P2 v3", "Premium v3"))])
def test_app_service_sku_names_match_the_price_list(sku, expected):
    assert app_service_sku(sku) == expected


def plan(sku, linux=True, capacity=2):
    return {"id": "/x/plan", "type": "Microsoft.Web/serverfarms", "location": "Sweden Central",
            "sku": {"name": sku, "capacity": capacity}, "kind": "linux" if linux else "app",
            "properties": {"reserved": linux}}


def test_linux_and_windows_plans_are_different_products():
    [linux] = price_rules(plan("P1v3"))
    [windows] = price_rules(plan("P1v3", linux=False))
    assert linux.query.product == "Azure App Service Premium v3 Plan - Linux"
    assert windows.query.product == "Azure App Service Premium v3 Plan"
    assert linux.quantity == 2 and linux.query.region == "swedencentral"


def test_free_plan_is_not_billed_hourly():
    assert isinstance(price_rules(plan("F1")), NotEstimated)


def test_private_endpoint_is_priced_in_the_global_region():
    [item] = price_rules({"id": "/x/pe", "type": "Microsoft.Network/privateEndpoints", "location": "swedencentral"})
    assert item.query.region == "Global" and item.query.meter == "Standard Private Endpoint"


@pytest.mark.parametrize("size, tier", [(30, "S4"), (32, "S4"), (33, "S6"), (1024, "S30"), (32767, "S80")])
def test_disk_size_maps_to_the_tier_it_is_billed_at(size, tier):
    assert standard_hdd_tier(size) == tier


def test_disk_rule_names_the_capacity_meter_only():
    [item] = price_rules({"id": "/x/d", "type": "Microsoft.Compute/disks", "location": "swedencentral",
                          "sku": {"name": "Standard_LRS"}, "properties": {"diskSizeGB": 30}})
    assert (item.query.sku, item.query.meter) == ("S4 LRS", "S4 LRS Disk")


def test_unmapped_things_are_said_out_loud():
    premium = price_rules({"id": "/x/d", "type": "Microsoft.Compute/disks", "sku": {"name": "Premium_LRS"},
                           "properties": {"diskSizeGB": 64}})
    storage = price_rules({"id": "/x/st", "type": "Microsoft.Storage/storageAccounts"})
    assert isinstance(premium, NotEstimated) and "Premium_LRS" in premium.reason
    assert isinstance(storage, NotEstimated) and storage.reason == "usage-based or not mapped"


def test_type_from_resource_id_handles_child_resources():
    rid = "/subscriptions/0/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/kv/secrets/s1"
    assert resource_type({"id": rid}) == "Microsoft.KeyVault/vaults/secrets"
