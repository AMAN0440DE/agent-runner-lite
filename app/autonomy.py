"""Governed autonomy: how much the agent is allowed to do on its own.

This is the smallest file in the project and one of the most important. An agent that can send
messages and update records needs a policy sitting between "the model asked for this" and "it
happened". That policy is one pure function.

TASK 1: evaluate_gate.
"""

from __future__ import annotations

from app.config import SETTINGS
from app.models import AutonomyLevel, GateDecision, ToolKind


def evaluate_gate(
    level: AutonomyLevel,
    tool_kind: ToolKind,
    writes_so_far: int,
    max_auto_writes: int = SETTINGS.max_auto_writes,
) -> GateDecision:
    """Decide how one tool call is allowed to proceed.

    Pure: four plain values in, one decision out. No I/O, no state, no side effects — which is
    what makes every branch testable in a few lines with no setup.

    Policy:
      - Reads are allowed at every autonomy level. Looking something up cannot break anything.
      - ``shadow``: writes are allowed but simulated. Nothing changes; we still record what the
        agent would have done, which is what makes shadow a zero-risk correctness check.
      - ``supervised``: every write stops and asks a reviewer.
      - ``autonomous``: writes are auto-approved while ``writes_so_far < max_auto_writes``.
        Once the budget is spent, further writes require approval. The boundary is a strict
        ``<`` — with ``max_auto_writes=2``, writes 0 and 1 are auto, write 2 asks.
    """
    if tool_kind == "read":
        return GateDecision(
            allow=True,
            reason=f"read tool: always allowed (level={level})",
        )

    if level == "shadow":
        return GateDecision(
            allow=True,
            simulate=True,
            reason="shadow: write is simulated, nothing changes",
        )

    if level == "supervised":
        return GateDecision(
            allow=False,
            requires_approval=True,
            reason="supervised: every write requires approval",
        )

    # autonomous
    if writes_so_far < max_auto_writes:
        return GateDecision(
            allow=True,
            reason=(
                f"autonomous: write {writes_so_far + 1} of {max_auto_writes} within budget"
            ),
        )

    return GateDecision(
        allow=False,
        requires_approval=True,
        reason=(
            f"autonomous: budget exhausted ({writes_so_far}/{max_auto_writes}); "
            "approval required"
        ),
    )