"""Learn's three-policy example ("Combined effect of multiple data policies") reproduced exactly."""
from dlpkit.evaluate import consolidated_groups, evaluate
from dlpkit.model import BUSINESS, NONBUSINESS, Policy

ALL = ["sharepoint", "twitter", "salesforce", "facebook", "faceapi", "outlook", "basecamp3", "adobesign", "azureblob", "box"]


def policy(name, business):
    return Policy(display_name=name, default=NONBUSINESS, groups={c: BUSINESS for c in business})


A = policy("A", ["sharepoint", "twitter", "salesforce", "outlook", "basecamp3"])
B = policy("B", ["sharepoint", "facebook", "faceapi", "outlook", "basecamp3"])
C = policy("C", ["facebook", "faceapi", "twitter", "salesforce", "outlook"])


def test_learn_example_gives_the_groups_on_the_page():
    groups = consolidated_groups(ALL, [A, B, C])
    expected = [
        ["outlook"],                                  # group 1
        ["basecamp3", "sharepoint"],                  # group 2
        ["salesforce", "twitter"],                    # group 3
        ["faceapi", "facebook"],                      # group 5
        ["adobesign", "azureblob", "box"],            # group 8
    ]
    assert sorted(groups) == sorted(expected)


def test_connectors_from_two_of_those_groups_can_not_share_a_flow():
    pols = [A, B, C]
    assert evaluate({"sharepoint", "basecamp3"}, pols) == []          # same group
    assert evaluate({"twitter", "salesforce"}, pols) == []
    v = evaluate({"sharepoint", "twitter"}, pols)                     # group 2 with group 3
    assert [x.kind for x in v] == ["mixed"]
    assert "A: Business" in v[0].message                              # the message names the policies


def test_a_single_policy_would_have_allowed_that_mix():
    assert evaluate({"sharepoint", "twitter"}, [A]) == []             # both Business in A alone
    assert evaluate({"sharepoint", "twitter"}, [A, B])                # B separates them


def test_two_policies_give_four_groups_at_most():
    assert len(consolidated_groups(ALL, [A, B])) <= 4
