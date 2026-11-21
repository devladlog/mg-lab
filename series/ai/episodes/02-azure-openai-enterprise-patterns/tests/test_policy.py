"""Static checks on the API Management policy, against the rules on the Learn policy reference pages."""
import re
import xml.etree.ElementTree as ET

import pytest

from aoai_gateway.usage import CONSUMED, REMAINING, REMAINING_QUOTA


@pytest.fixture
def policy(infra_dir):
    return ET.parse(infra_dir / "policies" / "aoai-api.xml").getroot()


def inbound_tags(policy):
    return [el.tag for el in policy.find("inbound")]


def test_sections_exist_and_inherit_base(policy):
    for section in ("inbound", "outbound", "on-error"):
        assert policy.find(section).find("base") is not None


def test_token_limit_has_required_attributes(policy):
    tl = policy.find("inbound/llm-token-limit")
    assert tl.get("counter-key") == "@(context.Subscription.Id)"
    assert tl.get("estimate-prompt-tokens") in ("true", "false")          # required by the policy
    assert tl.get("tokens-per-minute") or (tl.get("token-quota") and tl.get("token-quota-period"))
    assert tl.get("token-quota-period") in ("Hourly", "Daily", "Weekly", "Monthly", "Yearly")


def test_header_names_match_the_client(policy):
    tl = policy.find("inbound/llm-token-limit")
    assert tl.get("remaining-tokens-header-name") == REMAINING
    assert tl.get("remaining-quota-tokens-header-name") == REMAINING_QUOTA
    assert tl.get("tokens-consumed-header-name") == CONSUMED


def test_metric_policy_uses_at_most_five_custom_dimensions(policy):
    dims = policy.findall("inbound/llm-emit-token-metric/dimension")
    assert 1 <= len(dims) <= 5


def test_caller_credentials_are_dropped_before_the_backend(policy):
    tags = inbound_tags(policy)
    delete_key = [el for el in policy.find("inbound") if el.tag == "set-header" and el.get("name") == "api-key"]
    assert delete_key and delete_key[0].get("exists-action") == "delete"
    auth = [el for el in policy.find("inbound") if el.tag == "set-header" and el.get("name") == "Authorization"]
    assert auth[0].get("exists-action") == "override"
    mi = policy.find("inbound/authentication-managed-identity")
    assert mi.get("resource") == "https://cognitiveservices.azure.com"
    assert tags.index("authentication-managed-identity") < tags.index("set-backend-service")


def test_limits_run_before_routing(policy):
    tags = inbound_tags(policy)
    assert tags.index("llm-token-limit") < tags.index("set-backend-service")


def test_backend_pool_id_exists_in_bicep(policy, infra_dir):
    backend_id = policy.find("inbound/set-backend-service").get("backend-id")
    assert re.search(rf"name: '{backend_id}'", (infra_dir / "main.bicep").read_text())


def test_gateway_retry_is_small_and_buffers_the_body(policy):
    retry = policy.find("backend/retry")
    assert int(retry.get("count")) <= 2
    assert retry.find("forward-request").get("buffer-request-body") == "true"
