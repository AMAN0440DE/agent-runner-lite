"""Task 4a: retry logic for the model call.

Written BEFORE the implementation — see the commit history.

Two habits from the brief are baked into these tests:

  * assert on what should NOT have happened — `model.calls == 1` after a
    FatalError is what proves the fatal error was NOT retried. A test that
    only checks "it raised" would pass even if the loop retried three times
    first;
  * exercise every path through the retry loop — success on the first call,
    throttled once then success, throttled past the limit, fatal on the
    first call.
"""

from __future__ import annotations

import pytest

from app.config import SETTINGS
from app.model_client import (
    FatalError,
    MockModelClient,
    ThrottleError,
    complete_with_retry,
)


def test_returns_text_on_first_success():
    model = MockModelClient(['{"intent":"final","answer":"ok"}'])

    result = complete_with_retry(model, [])

    assert result == '{"intent":"final","answer":"ok"}'
    assert model.calls == 1


def test_retries_throttle_then_succeeds():
    model = MockModelClient(
        [
            ThrottleError("429 Too Many Requests"),
            ThrottleError("429 Too Many Requests"),
            '{"intent":"final","answer":"ok"}',
        ]
    )

    result = complete_with_retry(model, [])

    assert result == '{"intent":"final","answer":"ok"}'
    # three calls total: two retries, then success
    assert model.calls == 3


def test_raises_the_last_throttle_error_when_retries_run_out():
    # model_max_retries default is 3, so 1 initial + 3 retries = 4 calls before we give up.
    model = MockModelClient(
        [
            ThrottleError("429"),
            ThrottleError("429"),
            ThrottleError("429"),
            ThrottleError("429"),
            '{"intent":"final","answer":"never seen"}',
        ]
    )

    with pytest.raises(ThrottleError):
        complete_with_retry(model, [])

    # exhausted the budget: initial call + settings.model_max_retries retries
    assert model.calls == SETTINGS.model_max_retries + 1


def test_does_not_retry_a_fatal_error():
    model = MockModelClient(
        [
            FatalError("401 invalid api key"),
            '{"intent":"final","answer":"never seen"}',
        ]
    )

    with pytest.raises(FatalError):
        complete_with_retry(model, [])

    # the assertion that proves no retry happened
    assert model.calls == 1


def test_does_not_swallow_unexpected_exceptions():
    # A non-ModelError exception should propagate untouched — no retry, no rewrap.
    model = MockModelClient([ValueError("boom")])

    with pytest.raises(ValueError):
        complete_with_retry(model, [])

    assert model.calls == 1