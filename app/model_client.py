"""The seam between our code and a foundation model.

We never import a vendor SDK. We define the smallest interface we need (`ModelClient`) and code
against that. A real adapter for Anthropic, OpenAI or Bedrock would implement the same one method.
For this exercise the only implementation is a scripted mock, so everything runs offline with no
API keys, no network, and no cost — and every test gives the same answer every time.

PROVIDED: ModelClient, ModelError/ThrottleError/FatalError, MockModelClient.
TASK 4:   complete_with_retry.
"""

from __future__ import annotations

import time
from typing import Protocol, Union, runtime_checkable

from app.config import SETTINGS, Settings


class ModelError(Exception):
    """Base class for anything that goes wrong talking to the model."""


class ThrottleError(ModelError):
    """TRANSIENT. Rate limited, or the provider had a wobble (HTTP 429 / 5xx).

    Worth retrying: the same request may well succeed a moment later.
    """


class FatalError(ModelError):
    """PERMANENT. A malformed request, a bad API key, a model that doesn't exist (HTTP 400 / 401).

    Not worth retrying: it will fail identically every time, and retrying burns time and quota
    while the caller waits for an answer that isn't coming.
    """


@runtime_checkable
class ModelClient(Protocol):
    """Anything with this method can be used as our model."""

    def complete(self, messages: list[dict]) -> str:  # returns the model's raw text
        ...


class MockModelClient:
    """A model that reads from a script instead of thinking.

    `responses` is consumed one entry per `complete()` call:
      - a string is returned as the model's reply;
      - an Exception instance is RAISED.

    That second part is the useful bit for testing: a script of
        [ThrottleError("429"), '{"intent": "final", "answer": "ok"}']
    lets you test your retry logic without a flaky network. `calls` counts invocations, so a test
    can assert exactly how many times the model was hit.
    """

    def __init__(self, responses: list[Union[str, Exception]]):
        self._responses = list(responses)
        self._cursor = 0
        self.calls = 0

    def complete(self, messages: list[dict]) -> str:
        self.calls += 1
        if self._cursor >= len(self._responses):
            # Script ran out. Return a safe "we're done" so a buggy loop can't hang forever.
            return '{"intent": "final", "answer": "done"}'
        item = self._responses[self._cursor]
        self._cursor += 1
        if isinstance(item, Exception):
            raise item
        return item


def complete_with_retry(
    model: ModelClient, messages: list[dict], settings: Settings = SETTINGS
) -> str:
    """Call the model, retrying transient failures with exponential backoff.

    ``ThrottleError`` is TRANSIENT — the same request may succeed a moment later — so it is
    retried up to ``settings.model_max_retries`` times. Before each retry we sleep
    ``settings.model_backoff_base_seconds * 2**attempt``, with ``attempt`` starting at 0: the
    first retry waits ``base``, the second ``2*base``, the third ``4*base``. Doubling matters —
    hammering an overloaded provider every 10ms makes things worse for everyone.

    ``FatalError`` (and any other exception) is PERMANENT — it will fail identically every time
    — so it's raised immediately, with no retry. ``model.calls == 1`` after a ``FatalError`` is
    the assertion that proves no retry happened; a test that only checks "it raised" would pass
    even after three retries.

    If the retry budget runs out, the last ``ThrottleError`` is re-raised. We deliberately do
    NOT swallow it and do NOT return ``None`` — the caller needs to know the call failed.
    """
    last_attempt = settings.model_max_retries
    for attempt in range(last_attempt + 1):
        try:
            return model.complete(messages)
        except ThrottleError:
            if attempt >= last_attempt:
                raise
            time.sleep(settings.model_backoff_base_seconds * (2**attempt))

    # Unreachable: the loop above either returns or raises.
    raise AssertionError("complete_with_retry: exhausted attempts without returning or raising")