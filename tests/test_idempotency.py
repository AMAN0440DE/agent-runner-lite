"""Task 4b: idempotent `send_message`.

Written BEFORE the implementation — see the commit history.

Two habits from the brief are baked into these tests:

  * assert on the WORLD, not the return value — for idempotency, checking
    what `send_message` returned proves nothing. The bug being guarded
    against is the second email existing, so we assert on `ws.messages`;
  * cover the failure modes the tool is supposed to refuse — missing
    contact_id, missing idempotency_key, unknown contact — because those
    are the branches a naive implementation forgets.
"""

from __future__ import annotations

import pytest

from app.seed import CONTACTS
from app.tools import ToolError, Workspace


def _ws() -> Workspace:
    return Workspace(CONTACTS)


def test_same_key_only_sends_once():
    ws = _ws()

    first = ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")
    second = ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")

    # assert on the world, not the return value: the second message must not exist
    assert len(ws.messages) == 1
    # the original result is returned, correctly flagged
    assert first["message_id"] == second["message_id"]
    assert first["deduped"] is False
    assert second["deduped"] is True


def test_different_keys_send_twice():
    ws = _ws()

    ws.send_message(contact_id="c_1", body="one", idempotency_key="k1")
    ws.send_message(contact_id="c_1", body="two", idempotency_key="k2")

    assert len(ws.messages) == 2


def test_different_contacts_with_different_keys_both_send():
    ws = _ws()

    ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")
    ws.send_message(contact_id="c_2", body="hi", idempotency_key="k2")

    assert len(ws.messages) == 2


def test_requires_a_contact_id():
    ws = _ws()

    with pytest.raises(ToolError):
        ws.send_message(contact_id="", body="hi", idempotency_key="k1")

    assert ws.messages == []


def test_requires_an_idempotency_key():
    # A key is not optional — without one the caller cannot be protected.
    ws = _ws()

    with pytest.raises(ToolError):
        ws.send_message(contact_id="c_1", body="hi")

    assert ws.messages == []


def test_rejects_unknown_contact():
    ws = _ws()

    with pytest.raises(ToolError):
        ws.send_message(contact_id="c_999", body="hi", idempotency_key="k1")

    assert ws.messages == []


def test_result_carries_message_id_and_contact_id():
    ws = _ws()

    result = ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")

    assert result["contact_id"] == "c_1"
    assert result["message_id"].startswith("m_")
    assert ws.messages[0]["message_id"] == result["message_id"]
    assert ws.messages[0]["contact_id"] == "c_1"


def test_dedup_returns_the_original_message_id_even_after_other_sends():
    # Interleave a second, unrelated send between the two identical-key calls
    # to prove the cache is keyed on the idempotency key alone, not on position.
    ws = _ws()

    first = ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")
    ws.send_message(contact_id="c_2", body="other", idempotency_key="k2")
    second = ws.send_message(contact_id="c_1", body="hi", idempotency_key="k1")

    assert second["message_id"] == first["message_id"]
    assert second["deduped"] is True
    assert len(ws.messages) == 2