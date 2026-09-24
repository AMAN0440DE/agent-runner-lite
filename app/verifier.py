"""Behaviour-equivalence checking: did the agent do what it was supposed to, and nothing else?

An agent that finishes and says "done!" has told you nothing. The model's own summary of its work
is not evidence. So after every run we compare the side effects the task *expected* against the
effects that *actually happened*, and that diff is the verdict.

This is the part that makes shadow mode valuable. Effects recorded in shadow mode are simulated,
but the diff works exactly the same on them — so you can prove an agent would have behaved
correctly before you ever let it touch production.

TASK 2: verify.
"""

from __future__ import annotations

from app.models import Effect, ExpectedEffect, Run, Task, Verdict


def _matches(expected: ExpectedEffect, actual: Effect) -> bool:
    """True if ``actual`` satisfies ``expected``.

    Same tool name, and every key/value in ``expected.match`` appears in ``actual.args``.
    Subset, not equality: the expectation says "a message to c_1" and doesn't care what the
    body was, or that an idempotency key was attached.
    """
    if expected.tool != actual.tool:
        return False
    return all(actual.args.get(key) == value for key, value in expected.match.items())


def verify(task: Task, run: Run) -> Verdict:
    """Diff what was expected against what happened.

    Rules:
      1. An expectation is matched by an effect when the tool names are equal AND every
         key/value in the expectation's ``match`` appears in the effect's ``args`` (subset, not
         equality).
      2. Each actual effect can be spent at most once. Two identical expectations cannot both be
         satisfied by one send — that's the rule that catches the common bug of looping
         expectations against the full effect list each time.
      3. Effects no expectation claimed land in ``unexpected``. Extras are failures, not
         curiosities: an agent that did its job *and also* messaged three other people has not
         passed.
      4. ``passed`` iff nothing is missing AND nothing is unexpected.
      5. ``mode`` is the run's autonomy level; ``detail`` is a short human-readable summary.
      6. Simulated effects are treated exactly like real ones. That identity is the feature —
         it's what makes a shadow run a meaningful correctness proof.
    """
    spent: set[int] = set()
    matched: list[ExpectedEffect] = []
    missing: list[ExpectedEffect] = []

    for expected in task.expected_effects:
        for index, effect in enumerate(run.effects):
            if index in spent:
                continue
            if _matches(expected, effect):
                spent.add(index)
                matched.append(expected)
                break
        else:
            # No unspent effect satisfied this expectation.
            missing.append(expected)

    unexpected = [
        effect for index, effect in enumerate(run.effects) if index not in spent
    ]
    passed = not missing and not unexpected

    return Verdict(
        passed=passed,
        matched=matched,
        missing=missing,
        unexpected=unexpected,
        mode=run.autonomy,
        detail=(
            f"{len(matched)} matched, {len(missing)} missing, {len(unexpected)} unexpected"
        ),
    )