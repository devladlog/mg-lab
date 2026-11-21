"""One expression instead of a loop: same total, far fewer action runs.

Learn (limits page): Power Platform requests "are counted for all types of actions, including connector
actions, HTTP actions, and built-in actions, from initializing variables to a simple compose action".
flowkit counts every action run, loop iterations included.
"""
import pytest

from flowkit import run_flow

from conftest import sample


def rows(n):
    return {"rows": [{"reference": f"PR-{i:05d}", "amount": 100 + i} for i in range(n)]}


@pytest.mark.parametrize("n", [1, 25, 200])
def test_xpath_sum_matches_the_loop_with_fewer_actions(n):
    loop = run_flow(sample("total-with-apply-to-each.json"), rows(n))
    xp = run_flow(sample("total-with-xpath.json"), rows(n))
    expected = sum(100 + i for i in range(n))
    assert loop.actions["Total"].outputs == expected
    assert xp.actions["Total"].outputs == expected
    assert loop.executions == n + 3   # Initialize + Apply to each + n increments + Compose
    assert xp.executions == 1
