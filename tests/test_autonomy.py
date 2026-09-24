"""Task 1: the governance decision table.

Written BEFORE the implementation — see the commit history. Every branch of `evaluate_gate`
is reachable in one line with no setup, so the whole policy fits in one parametrized test.
"""

from __future__ import annotations

import pytest

from app.autonomy import evaluate_gate


@pytest.mark.parametrize(
    # level, kind, writes_so_far, max_auto, allow, simulate, requires_approval
    "level,kind,writes_so_far,max_auto,allow,simulate,requires_approval",
    [
        # reads: always allowed, at every level, no matter how many writes already happened
        ("shadow", "read", 0, 2, True, False, False),
        ("supervised", "read", 0, 2, True, False, False),
        ("autonomous", "read", 0, 2, True, False, False),
        ("autonomous", "read", 5, 2, True, False, False),
        # shadow writes: allowed but simulated, budget irrelevant
        ("shadow", "write", 0, 2, True, True, False),
        ("shadow", "write", 9, 2, True, True, False),
        # supervised writes: always ask
        ("supervised", "write", 0, 2, False, False, True),
        ("supervised", "write", 1, 2, False, False, True),
        # autonomous writes within budget
        ("autonomous", "write", 0, 2, True, False, False),
        ("autonomous", "write", 1, 2, True, False, False),
        # autonomous at/over budget — the boundary must be exact:
        # with max_auto_writes=2, writes 0 and 1 are auto, write 2 asks.
        ("autonomous", "write", 2, 2, False, False, True),
        ("autonomous", "write", 3, 2, False, False, True),
        # edge: zero budget means no unsupervised writes at all
        ("autonomous", "write", 0, 0, False, False, True),
    ],
)
def test_evaluate_gate_decision_table(
    level,
    kind,
    writes_so_far,
    max_auto,
    allow,
    simulate,
    requires_approval,
):
    decision = evaluate_gate(level, kind, writes_so_far, max_auto)
    assert decision.allow is allow
    assert decision.simulate is simulate
    assert decision.requires_approval is requires_approval
    # The reason ends up in the audit trail, so it must always be populated.
    assert decision.reason