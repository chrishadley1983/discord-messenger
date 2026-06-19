"""Regression test for the WhatsApp instance-filter privacy fix.

Background
----------
The `chris-whatsapp` Evolution instance is paired to Chris's personal number
and exists only to feed the Second Brain seed adapter with his chat history.
It POSTs to the same `/whatsapp/webhook` endpoint as Peter's own instance
(`peter-whatsapp`). Without an instance guard, every message in Chris's
WhatsApp -- including private threads with other people -- flows into Peter's
live handler, and Peter auto-replies (from his own number) to anyone
allowlisted.

`_handle_message(body)` guards against this: it drops any `messages.upsert`
whose `instance` is not `EVOLUTION_INSTANCE`.

This test proves:
  (a) a payload with "instance": "chris-whatsapp" is DROPPED before reaching
      any downstream processing (the dedup seam `_is_duplicate` is NEVER hit).
  (b) a payload with "instance": "peter-whatsapp" (== EVOLUTION_INSTANCE) is
      processed PAST the guard (the dedup seam `_is_duplicate` IS reached).

We assert on `_is_duplicate`, which is the first thing called after the guard
for any non-fromMe incoming message. By giving the message an *unknown* sender
(not in the allowlist), execution returns cleanly right after the dedup check,
so no Evolution API / Discord / network call is ever made.
"""
import asyncio
from unittest.mock import patch

import pytest

from hadley_api import whatsapp_webhook
from hadley_api.whatsapp_webhook import _handle_message, EVOLUTION_INSTANCE


def _make_body(instance: str) -> dict:
    """A realistic messages.upsert body for an incoming (non-fromMe) DM from an
    unknown sender, so processing stops right after the dedup check."""
    return {
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": "447000000000@s.whatsapp.net",
                "fromMe": False,
                "id": "REGRESSIONTESTMSGID0001",
            },
            "pushName": "Some Random Person",
            "message": {"conversation": "private message not for Peter"},
        },
    }


@pytest.mark.asyncio
async def test_foreign_instance_is_dropped():
    """chris-whatsapp payloads must be dropped before any downstream work."""
    foreign = "chris-whatsapp"
    assert foreign != EVOLUTION_INSTANCE  # guard precondition

    with patch.object(whatsapp_webhook, "_is_duplicate", return_value=False) as dedup:
        await _handle_message(_make_body(foreign))

    assert dedup.call_count == 0, (
        "PRIVACY LEAK: a message from the foreign 'chris-whatsapp' instance "
        "reached the dedup/processing path. The instance guard failed to drop it."
    )


@pytest.mark.asyncio
async def test_own_instance_is_processed_past_guard():
    """peter-whatsapp payloads must pass the guard and reach processing."""
    with patch.object(whatsapp_webhook, "_is_duplicate", return_value=False) as dedup:
        await _handle_message(_make_body(EVOLUTION_INSTANCE))

    assert dedup.call_count == 1, (
        "Peter's own instance was blocked by the guard -- it should be "
        "processed past the instance check and reach the dedup seam."
    )


if __name__ == "__main__":
    # Standalone fallback: drive the coroutines directly without pytest.
    def _run():
        results = []
        for label, instance, expected_calls in (
            ("foreign chris-whatsapp DROPPED", "chris-whatsapp", 0),
            ("own peter-whatsapp PROCESSED", EVOLUTION_INSTANCE, 1),
        ):
            with patch.object(whatsapp_webhook, "_is_duplicate", return_value=False) as dedup:
                asyncio.run(_handle_message(_make_body(instance)))
            ok = dedup.call_count == expected_calls
            results.append(ok)
            print(f"[{'PASS' if ok else 'FAIL'}] {label} "
                  f"(_is_duplicate called {dedup.call_count}x, expected {expected_calls})")
        print("OVERALL:", "PASS" if all(results) else "FAIL")

    _run()
