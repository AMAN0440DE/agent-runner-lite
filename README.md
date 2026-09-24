# Agent Runner Lite — Intern Take-Home

Thanks for taking the time on this. You'll build a small **governed agent runner**: a service that
drives an AI agent through a tool-use loop, decides what the agent is allowed to do on its own, and
then checks that it actually did what was asked — and nothing more.

The full brief — the six tasks, what we look for, and the ground rules — is in **`BRIEF.md`**.
**Read that first.** This file is just how to run things, plus a map of the code, and it's where you
write up your work when you're done.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -q                                             # the example tests pass on a fresh checkout
uvicorn app.main:app --reload                         # http://127.0.0.1:8000/docs
```

Requires **Python 3.11+**. No API keys, no network, no external services — the language model is a
script (`app/seed.py`), so everything is deterministic and offline.

On a fresh checkout the app imports and `pytest` is green, but the six functions you're implementing
raise `NotImplementedError` (and `POST /runs` returns a 501). That's expected. Search the project for
`TODO(candidate)` to find them — there are six, numbered by task.

Nothing is persisted. Restart the server and your tasks and runs are gone. That's fine, don't work
around it.

## Where things are

```
app/
  models.py          the whole data contract — READ THIS FIRST, it's the map
  config.py          settings, all overridable by env var
  seed.py            toy contacts + 11 scripted model conversations
  store.py           two dicts standing in for a database
  model_client.py    TASK 4a — complete_with_retry     (mock model provided)
  tools.py           TASK 4b — send_message            (read tools + update_contact provided)
  autonomy.py        TASK 1  — evaluate_gate
  verifier.py        TASK 2  — verify
  agent.py           TASK 3  — run_agent               (five helpers provided)
  api.py             TASK 5  — start_run               (three other routes provided)
  main.py            the FastAPI app
tests/
  helpers.py         make_run() — builds an isolated run in one line
  conftest.py        store reset + a `client` fixture for HTTP tests
  test_example.py    four example tests showing the shapes you'll want
```

## A suggested first hour

If you're not sure where to start:

1. `pip install -r requirements.txt && pytest -q`. Green? Good.
2. Read **`app/models.py`** top to bottom. It's commented and it's the whole data model — most of
   the "what shape do I return?" questions are answered there.
3. Read **`app/seed.py`** to see what the mock model does. This is the trick that makes the whole
   thing testable, and it's worth understanding before anything else.
4. Open **`app/autonomy.py`** (Task 1). Write the tests for it first — `test_example.py` has a
   `parametrize` example to copy. Watch them fail, then make them pass.
5. Then `app/verifier.py` (Task 2), same way.

By then you'll have the shape of the codebase and two of the six tasks done.

## Useful to know

- **The scenarios in `app/seed.py` are your test fixtures.** There's one for each path you need to
  handle: `send_followup` (the happy path), `unknown_tool` (a hallucinated tool name),
  `tool_error` (a tool that fails), `three_writes` (the autonomy budget), `never_finishes` (the
  `max_steps` cap), `flaky_provider` (throttled then fine), `bad_credentials` (fatal, don't retry),
  `bad_json_then_good` and `always_bad_json` (malformed model output). Read the comments there.
- **`tests/helpers.py::make_run`** gives you a Run and its dependencies in one line, isolated. Use it
  for every loop test.
- **Everything is synchronous.** Plain `def`, `time.sleep`, no `await` anywhere. If you find
  yourself reaching for `asyncio`, you've gone off the path.
- **Settings are injected, not global.** Your functions take `settings`, so a test can say "budget
  of 1, retry twice" without touching the environment:
  `make_run(script, settings=replace(SETTINGS, max_auto_writes=1))`.
- Once Task 5 is done, `http://127.0.0.1:8000/docs` gives you a UI to create a task and start a run
  without writing any curl. Good for a sanity check that pytest can't give you.

---

# Your write-up

### What's working

All six tasks are complete. `pip install -r requirements.txt && pytest` is green on Python 3.11+,
and the project runs end-to-end via `uvicorn app.main:app --reload` → `/docs`.

- **Task 1 — `evaluate_gate`.** Pure decision function. Reads always pass; `shadow` simulates
  writes; `supervised` requires approval on every write; `autonomous` allows writes while
  `writes_so_far < max_auto_writes` and asks thereafter. The `<` boundary is the one the brief
  flags as easy to get wrong, and there's a dedicated parametrized row for it
  (`autonomous, write, 2, 2 → requires approval`).
- **Task 2 — `verify`.** Subset matching against `ExpectedEffect.match`. A `set[int]` of spent
  effect indices guarantees one effect can satisfy at most one expectation, and any effect no
  expectation claimed lands in `unexpected` and fails the verdict. Simulated effects are handled
  identically to real ones.
- **Task 3 — `run_agent`.** One tool call per turn, bounded by `max_steps`. Only two things end a
  run: the model saying `final`, or something unrecoverable (FatalError, malformed model output,
  step budget exhausted). Unknown tool, tool error, and reviewer rejection are all observations
  fed back to the model.
- **Task 4a — `complete_with_retry`.** Exponential backoff on `ThrottleError`, straight re-raise
  on `FatalError` and on anything else.
- **Task 4b — `send_message`.** Remembers each idempotency key it has handled; a repeat returns
  the original result with `deduped: True` and does not append to `Workspace.messages`.
- **Task 5 — `POST /runs`.** Looks up the task (404 if missing), builds a per-run Workspace and
  registry, drives `run_agent`, returns the finished run.
- **Task 6 — tests.** 8 test modules; TDD on Tasks 1, 2, 4a and 4b (test commits precede their
  matching feat commits in the history).

Nothing is half-finished. The optional extras in the brief (per-tool gate override, richer
`Verdict` summaries, structured logging) are deliberately not attempted — see *What I'd do next*.

### Design decisions

**The loop is deliberately flat.** Each turn is a short sequence — decide, maybe finish, find the
tool, gate it, run it, tell the model — and the recoverable branches all end in `continue`. That
makes "an unknown tool is normal" visible in the code: there is one `continue` per recoverable
kind of bad news.

**What ends a run vs what becomes an observation.** A tool that doesn't exist, a tool that errors,
and a reviewer who says no are all normal — they become observations and the loop carries on.
Everything else (FatalError, malformed model output that survives re-prompts, the step budget)
marks the run `failed` with `run.error` set and never raises out of `run_agent`. The outer
`try/except` is the belt-and-braces version of the same rule: a FatalError from the provider must
not escape to the caller.

**Idempotency key handling.** `_execute` generates a stable key of `f"{run.id}:{len(run.steps)}"`
for each `send_message` call — unique per (run, step) and identical across retries of the same
logical send, which is exactly the property the tool needs. `Workspace._idem` caches the *stored*
result without the `deduped` flag, so a dedup can report `deduped: True` honestly without
overwriting the cached value.

**The gate's `reason` is not decorative.** It ends up in the run's audit trail as a `gate` step
for every tool call — reads included. The transcript answers "why was this allowed?" directly,
which the brief says is the first question anyone asks about an agent that did something
surprising.

**Assumptions the brief left ambiguous, and my calls:**

- *Read tools after the write budget is exhausted.* Allowed. The budget is specifically a
  write-budget; reads are non-mutating, and stopping reads would make a "researcher" agent unable
  to finish its job once it had sent its allowed messages.
- *Idempotency key vs the contact-not-found check.* The contact check runs before the cache
  consult, so a stale key against a vanished contact raises rather than silently returning a
  cached success. Same ordering as `update_contact`.
- *Effect args include the auto-generated key.* The Effect's `args` reflect what actually touched
  the world — captured after `_execute` mutates them. `ExpectedEffect.match` is a subset check, so
  this is invisible to tasks that don't match on the key, and correct for tasks that do.
- *A completed run can still have `verdict.passed == False`.* "The model finished" and "the work
  was correct" are separate outcomes. A completed-but-unverified run is a signal (the transcript
  shows what was missing or extra), not a failure of the run itself.

### Testing approach

**I wrote the Task 1, 2, 4a and 4b tests before their implementations**, ran them, watched them
fail, then made them pass. The commit history shows the sequence (`test(autonomy): …` before
`feat(autonomy): …`, and the same for verifier, model_client and tools).

- **The gate is a decision table**, so it's a single `@pytest.mark.parametrize` with one row per
  (level, kind, writes_so_far, max_auto, expected). Fifteen rows, and a failure tells you exactly
  which input combination broke. The `autonomous, write, 2, 2` row is the boundary case the brief
  warns about.
- **The verifier has one test per outcome** — pass, missing, unexpected — plus two tests for the
  rules people get wrong: *one effect can't satisfy two expectations* and *match is a subset, not
  equality*. There's also an explicit test that simulated and real effects produce identical
  verdicts.
- **The loop is tested through the ready-made scenarios** in `app/seed.py`. Each scenario exists
  to exercise one path; using them directly makes the tests read like the brief.
- **Two habits from the brief I deliberately adopted:**
  - *Assert on the world, not the return value.* `test_same_key_only_sends_once` asserts
    `len(ws.messages) == 1`, and `test_shadow_records_simulated_effect_…` asserts
    `deps.workspace.messages == []`. Checking the return value would prove nothing about whether
    the second email exists.
  - *Assert on what should NOT have happened.* `test_does_not_retry_a_fatal_error` asserts
    `model.calls == 1`. A test that only checks "it raised" passes even if the retry loop ran
    three times first.

**What I deliberately did not test:** the exact number of backoff sleeps (asserting `model.calls`
catches a broken retry loop without coupling to sleep values), the exact wording of `Step.message`
strings (they're for humans reading the audit trail; asserting on them makes tests brittle), and
FastAPI's `response_model` serialisation beyond what the E2E test already covers.

### What was hardest

Two things genuinely took longer than I expected.

**First: the verifier's "one effect, one expectation" rule.** My first cut looped expectations and,
for each, scanned the whole effect list for a match. It passed the obvious tests and was wrong:
two identical expectations, one effect, and both counted as matched. Re-reading the brief —
"if you loop over expectations and search the full list of effects each time, a single effect will
satisfy every expectation that looks like it" — made me re-read my own code and realise I had
written exactly the pattern being warned about. The fix is a `set[int]` of spent indices threaded
through both loops, which is two lines but changes the correctness completely. There's now an
explicit test for it (`test_one_effect_cannot_satisfy_two_expectations`).

**Second: the loop's control flow.** My first version used `if intent.intent == "final": …`
followed by a separate `if intent.intent == "tool_use": …` and fell off the end of the loop body,
which meant the "model never finished" case silently left `run.status == "running"`. The brief
calls this out — "a caller polling this run would wait forever" — and the right tool turned out to
be Python's `for…else`: the `else` only fires if the loop completed without `break`, which is
exactly "the model never said `final`". It reads much more clearly than a `sentinel = False` flag
and doesn't leave a dead variable around.

### What I'd do next

With another day, in rough priority order:

1. **A per-tool gate override**, so `send_message` can be forced through approval even under
   `autonomous` while `update_contact` stays on the budget. This is the most obvious product gap —
   the current policy is uniform across write tools.
2. **A richer `Verdict.detail`** naming *which* expectation went missing (e.g.
   `"missing: send_message(contact_id='c_1')"`). The current summary is fine for a glance but
   you'd want specifics in a real ops review.
3. **Structured logging of each step** with the run id as a correlation id, so a run can be
   followed through logs the way it can be followed through `run.steps`.
4. **A larger end-to-end HTTP matrix** — one case per autonomy level through the `client` fixture,
   plus a case that drives `three_writes` under `supervised` with `reviewer_approves=False` and
   asserts the run still completes cleanly.
5. **Property-based tests** (`hypothesis`) for `verify`, generating arbitrary expectation/effect
   lists and asserting invariants like `len(matched) + len(missing) == len(expected)` and
   `spent indices ⊆ effect indices`. Would be a good stress test for the spent-index logic.

### Time spent

Roughly **5 hours** across the six tasks plus the write-up. The verifier and the loop were the
two biggest chunks (about 1h15 each including their tests); the gate, retry, idempotency and API
tasks together were about 2h; the rest was the README and re-reading my own code against the
brief.