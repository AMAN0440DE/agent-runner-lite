"""Task 2: behaviour-equivalence.

Written BEFORE the implementation — see the commit history. One test per outcome (pass,
missing, unexpected), plus two tests for the rules the brief calls out as easy to get wrong:
one effect can satisfy at most one expectation, and `match` is a subset check, not equality.
There's also an explicit test that simulated effects produce identical verdicts to real ones —
that identity is what makes a shadow run a real correctness proof.
"""

from __future__ import annotations

from app.models import Effect, ExpectedEffect, Run, Task
from app.verifier import verify


def _task(*expected: ExpectedEffect) -> Task:
    return Task(id="t", goal="g", scenario="test", expected_effects=list(expected))


def _run(*effects: Effect, autonomy: str = "autonomous") -> Run:
    return Run(id="r", task_id="t", autonomy=autonomy, effects=list(effects))


# --- one test per outcome ---


def test_passes_when_everything_expected_happened_and_nothing_else():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run(Effect(tool="send_message", args={"contact_id": "c_1", "body": "hi"}))

    verdict = verify(task, run)

    assert verdict.passed is True
    assert len(verdict.matched) == 1
    assert verdict.missing == []
    assert verdict.unexpected == []


def test_flags_a_missing_effect():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run()

    verdict = verify(task, run)

    assert verdict.passed is False
    assert len(verdict.missing) == 1
    assert verdict.missing[0].tool == "send_message"
    assert verdict.matched == []
    assert verdict.unexpected == []


def test_flags_an_unexpected_effect():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run(
        Effect(tool="send_message", args={"contact_id": "c_1"}),
        Effect(tool="send_message", args={"contact_id": "c_2"}),  # nobody asked for this
    )

    verdict = verify(task, run)

    assert verdict.passed is False
    assert len(verdict.matched) == 1
    assert len(verdict.unexpected) == 1
    assert verdict.unexpected[0].args["contact_id"] == "c_2"


# --- the two rules that are easy to get wrong ---


def test_one_effect_cannot_satisfy_two_expectations():
    # Two identical expectations but only one send actually happened:
    # exactly one is matched, the other is missing.
    task = _task(
        ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}),
        ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}),
    )
    run = _run(Effect(tool="send_message", args={"contact_id": "c_1"}))

    verdict = verify(task, run)

    assert verdict.passed is False
    assert len(verdict.matched) == 1
    assert len(verdict.missing) == 1


def test_match_is_subset_not_equality():
    # The expectation only pins contact_id; the actual effect carries extra args
    # (body, idempotency_key) which must not prevent a match.
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run(
        Effect(
            tool="send_message",
            args={
                "contact_id": "c_1",
                "body": "hi",
                "idempotency_key": "r_1:2",
            },
        )
    )

    verdict = verify(task, run)

    assert verdict.passed is True
    assert len(verdict.matched) == 1


def test_wrong_tool_name_does_not_match():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run(Effect(tool="update_contact", args={"contact_id": "c_1"}))

    verdict = verify(task, run)

    assert verdict.passed is False
    assert verdict.missing == task.expected_effects
    assert len(verdict.unexpected) == 1


# --- simulated effects are first-class citizens ---


def test_simulated_effects_produce_the_same_verdict_as_real_ones():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    real = _run(
        Effect(tool="send_message", args={"contact_id": "c_1"}, simulated=False)
    )
    simulated = _run(
        Effect(tool="send_message", args={"contact_id": "c_1"}, simulated=True)
    )

    assert verify(task, real).passed is True
    assert verify(task, simulated).passed is True


# --- the summary a human reads ---


def test_mode_and_detail_are_populated():
    task = _task(ExpectedEffect(tool="send_message", match={"contact_id": "c_1"}))
    run = _run(
        Effect(tool="send_message", args={"contact_id": "c_1"}),
        autonomy="shadow",
    )

    verdict = verify(task, run)

    assert verdict.mode == "shadow"
    assert "matched" in verdict.detail
    assert "missing" in verdict.detail
    assert "unexpected" in verdict.detail