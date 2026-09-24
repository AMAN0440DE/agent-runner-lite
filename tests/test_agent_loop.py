"""Task 3 tests: the loop, exercised through the ready-made scenarios in app/seed.py.

Each scenario in seed.py exists to drive one path through the loop. Using them directly makes
these tests read like the brief, and it means a change to the scenarios (say, a new one for a
new failure mode) shows up as a new test here rather than as an untested code path.

Uses `make_run` from tests/helpers.py: one line gives you an isolated Run + AgentDeps backed by
a fresh Store and Workspace, so tests can't contaminate each other and there's nothing to reset.
"""

from __future__ import annotations

from dataclasses import replace

from app.agent import run_agent
from app.config import SETTINGS
from app.models import ExpectedEffect
from app.seed import SCENARIOS
from tests.helpers import make_run


# ─────────────────────────────────────────────────────────────────────────────────────────
# Happy paths
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_default_scenario_completes_with_no_effects():
    """The simplest path: the model finishes immediately, no tools, no writes."""
    run, deps = make_run(SCENARIOS["default"])

    run_agent(run, deps)

    assert run.status == "completed"
    assert run.effects == []
    assert run.verdict is not None
    assert run.verdict.passed is True
    # only the final step, no tool steps at all
    assert [s.type for s in run.steps] == ["final"]


def test_send_followup_autonomous_records_one_effect_and_passes_verification():
    """The normal happy path: read, one write, finish. Effect recorded, workspace changed."""
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})]
    run, deps = make_run(SCENARIOS["send_followup"], expected=expected)

    run_agent(run, deps)

    assert run.status == "completed"
    assert len(run.effects) == 1
    assert run.effects[0].tool == "send_message"
    assert run.effects[0].simulated is False
    assert run.verdict is not None
    assert run.verdict.passed is True
    # the write actually happened in the world
    assert len(deps.workspace.messages) == 1
    assert deps.workspace.messages[0]["contact_id"] == "c_1"


def test_send_followup_under_supervised_with_approval_still_completes():
    """Same scenario, supervised + reviewer approves: one write, one matched effect."""
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})]
    run, deps = make_run(
        SCENARIOS["send_followup"],
        autonomy="supervised",
        expected=expected,
        reviewer_approves=True,
    )

    run_agent(run, deps)

    assert run.status == "completed"
    assert len(run.effects) == 1
    assert run.verdict is not None and run.verdict.passed is True
    assert len(deps.workspace.messages) == 1
    # the reviewer step exists and it's ok=True
    reviewer_steps = [s for s in run.steps if "reviewer" in s.message]
    assert len(reviewer_steps) == 1
    assert reviewer_steps[0].ok is True


# ─────────────────────────────────────────────────────────────────────────────────────────
# Shadow mode
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_shadow_records_simulated_effect_and_leaves_the_world_untouched():
    """The whole point of shadow: a correctness proof with zero real-world impact."""
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})]
    run, deps = make_run(
        SCENARIOS["send_followup"],
        autonomy="shadow",
        expected=expected,
    )

    run_agent(run, deps)

    assert run.status == "completed"
    assert len(run.effects) == 1
    assert run.effects[0].simulated is True
    assert run.verdict is not None
    assert run.verdict.passed is True
    # assert on the world, not on the effects list: nothing really happened
    assert deps.workspace.messages == []


# ─────────────────────────────────────────────────────────────────────────────────────────
# Recoverable bad news
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_unknown_tool_is_an_observation_not_a_crash():
    """The model invents a tool name. The loop feeds it back and carries on."""
    run, deps = make_run(SCENARIOS["unknown_tool"])

    run_agent(run, deps)

    assert run.status == "completed"
    # a failed tool_result step exists for the hallucinated tool
    failed = [s for s in run.steps if s.type == "tool_result" and s.ok is False]
    assert len(failed) == 1
    assert failed[0].tool == "archive_contact"
    # no effects were recorded for the missing tool
    assert run.effects == []


def test_tool_error_is_recoverable():
    """The tool exists but raises ToolError. Also recoverable."""
    run, deps = make_run(SCENARIOS["tool_error"])

    run_agent(run, deps)

    assert run.status == "completed"
    failed = [s for s in run.steps if s.type == "tool_result" and s.ok is False]
    assert len(failed) == 1
    assert failed[0].tool == "get_contact"
    assert run.effects == []


def test_reviewer_rejection_is_not_a_crash():
    """Supervised + reviewer says no. The write is skipped, the model can still finish."""
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})]
    run, deps = make_run(
        SCENARIOS["send_followup"],
        autonomy="supervised",
        expected=expected,
        reviewer_approves=False,
    )

    run_agent(run, deps)

    # The model still finishes (it says "final"), so the run is completed...
    assert run.status == "completed"
    # ...but the write never happened, so no effect was recorded.
    assert run.effects == []
    # ...and the world is untouched.
    assert deps.workspace.messages == []
    # The verdict correctly reports the missing expectation.
    assert run.verdict is not None
    assert run.verdict.passed is False
    assert len(run.verdict.missing) == 1


# ─────────────────────────────────────────────────────────────────────────────────────────
# Budget
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_three_writes_under_autonomous_with_budget_of_1_gates_later_writes():
    """max_auto_writes=1: write #1 auto, writes #2 and #3 go through the reviewer."""
    run, deps = make_run(
        SCENARIOS["three_writes"],
        settings=replace(SETTINGS, max_auto_writes=1),
    )

    run_agent(run, deps)

    assert run.status == "completed"
    # reviewer approves by default, so all three writes went through
    assert len(run.effects) == 3
    # exactly two reviewer gate steps: for writes #2 and #3
    reviewer_gates = [s for s in run.steps if "reviewer" in s.message]
    assert len(reviewer_gates) == 2


def test_three_writes_under_autonomous_with_default_budget_gates_only_the_third():
    """Default max_auto_writes=2: writes #1 and #2 auto, write #3 goes to the reviewer."""
    run, deps = make_run(SCENARIOS["three_writes"])

    run_agent(run, deps)

    assert run.status == "completed"
    assert len(run.effects) == 3
    reviewer_gates = [s for s in run.steps if "reviewer" in s.message]
    assert len(reviewer_gates) == 1


# ─────────────────────────────────────────────────────────────────────────────────────────
# Hard failures — the loop must end, not hang or raise
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_never_finishes_ends_failed_at_max_steps():
    """The model never says 'final'. max_steps is what saves us."""
    run, deps = make_run(
        SCENARIOS["never_finishes"],
        settings=replace(SETTINGS, max_steps=3),
    )

    run_agent(run, deps)

    assert run.status == "failed"
    assert run.error is not None
    assert "max_steps" in run.error or "3" in run.error
    # no verdict is computed for a failed run
    assert run.verdict is None


def test_bad_credentials_fails_without_raising_out_of_run_agent():
    """A FatalError from the model must not escape run_agent — the run fails, the caller lives."""
    run, deps = make_run(SCENARIOS["bad_credentials"])

    run_agent(run, deps)  # must NOT raise

    assert run.status == "failed"
    assert run.error is not None
    assert "FatalError" in run.error


def test_always_bad_json_fails_cleanly():
    """The model never produces valid JSON. The run fails after _decide gives up."""
    run, deps = make_run(SCENARIOS["always_bad_json"])

    run_agent(run, deps)

    assert run.status == "failed"
    assert run.error is not None


# ─────────────────────────────────────────────────────────────────────────────────────────
# Transient provider wobble
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_flaky_provider_succeeds_after_retries():
    """Two ThrottleErrors, then success — the retry logic recovers and the run completes."""
    run, deps = make_run(SCENARIOS["flaky_provider"])

    run_agent(run, deps)

    assert run.status == "completed"
    # the mock counted three invocations: two throttles + one success
    assert deps.model.calls == 3


# ─────────────────────────────────────────────────────────────────────────────────────────
# Audit trail
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_audit_trail_records_a_gate_step_for_every_tool_call():
    """Governed autonomy is worthless if you can't show your work: every tool call gets a gate."""
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})]
    run, deps = make_run(SCENARIOS["send_followup"], expected=expected)

    run_agent(run, deps)

    # send_followup calls search_contacts then send_message, then finishes.
    tool_calls = [s for s in run.steps if s.type == "tool_call"]
    gate_steps = [s for s in run.steps if s.type == "gate"]
    assert len(tool_calls) == 2
    assert len(gate_steps) == 2  # one gate decision per tool call


def test_step_indices_are_sequential_from_zero():
    """Step.index should read like a numbered transcript."""
    run, deps = make_run(SCENARIOS["send_followup"])

    run_agent(run, deps)

    assert [s.index for s in run.steps] == list(range(len(run.steps)))