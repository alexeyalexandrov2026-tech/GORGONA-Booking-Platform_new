"""I3 clock history, corrections and decisions against real PostgreSQL."""

from dataclasses import dataclass
from uuid import uuid7

import httpx
import pytest

from tests.integration import test_shift_changes as shared
from tests.integration.booking_support import at
from tests.integration.test_shift_changes import Changes

pytestmark = pytest.mark.anyio
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@dataclass(frozen=True)
class Times:
    changes: Changes

    @property
    def base(self) -> str:
        return self.changes.workforce.base

    async def start(
        self, key: str | None = None, identifier: str | None = None, **extra: object
    ) -> httpx.Response:
        return await self.changes.workforce.client.put(
            self.base + f"/time-entries/{identifier or uuid7()}",
            headers={**self.changes.left_headers, "Idempotency-Key": key or str(uuid7())},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "staff_profile_id": self.changes.left_profile,
                "starts_at": at(10).isoformat(),
                **extra,
            },
        )

    async def command(
        self,
        entry: dict[str, object],
        action: str,
        headers: dict[str, str] | None = None,
        key: str | None = None,
        **extra: object,
    ) -> httpx.Response:
        return await self.changes.workforce.client.post(
            self.base + f"/time-entries/{entry['entry_id']}/events",
            headers={
                **(headers or self.changes.left_headers),
                "Idempotency-Key": key or str(uuid7()),
            },
            json={
                "schema_version": 1,
                "expected_revision": entry["revision"],
                "action": action,
                **extra,
            },
        )


@pytest.fixture
def times(changes: Changes) -> Times:
    return Times(changes)


async def test_clock_break_close_approval_and_original_receipt(times: Times) -> None:
    created = await times.start()
    assert created.status_code == 200, created.text
    entry = dict(created.json())
    assert entry["status"] == "open"
    assert entry["out_of_schedule"] is True
    assert entry["effective"] is None
    started = await times.command(entry, "break_start", at=at(10, 20).isoformat())
    assert started.status_code == 200, started.text
    ended = await times.command(dict(started.json()), "break_end", at=at(10, 30).isoformat())
    assert ended.status_code == 200, ended.text
    prior, key = dict(ended.json()), str(uuid7())
    closed = await times.command(prior, "clock_out", key=key, at=at(11).isoformat())
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "proposed"
    assert closed.json()["worked_microseconds"] == 50 * 60 * 1_000_000
    assert closed.json()["effective"] is None
    approved = await times.command(dict(closed.json()), "approve", times.changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["effective"]["revision"] == 5
    assert approved.json()["self_approved"] is False
    replay = await times.command(prior, "clock_out", key=key, at=at(11).isoformat())
    assert replay.status_code == 200, replay.text
    assert replay.json() == closed.json()


async def test_three_corrections_keep_history_and_last_approved_time(times: Times) -> None:
    created = await times.start()
    assert created.status_code == 200, created.text
    closed = await times.command(dict(created.json()), "clock_out", at=at(11).isoformat())
    approved = await times.command(dict(closed.json()), "approve", times.changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    current = dict(approved.json())
    for minute in (10, 20, 30):
        corrected = await times.command(
            current,
            "correct",
            starts_at=at(10).isoformat(),
            ends_at=at(11, minute).isoformat(),
            breaks=[],
            reason=f"FAKE correction {minute}",
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["effective"] == current["effective"]
        decided = await times.command(
            dict(corrected.json()), "approve", times.changes.workforce.headers
        )
        assert decided.status_code == 200, decided.text
        current = dict(decided.json())
    history = await times.changes.workforce.client.get(
        times.base + f"/my-time-entries/{current['entry_id']}/history",
        headers=times.changes.left_headers,
    )
    assert history.status_code == 200, history.text
    assert [item["revision"] for item in history.json()["items"]] == list(range(1, 10))
    assert [item["reason"] for item in history.json()["items"] if item["action"] == "correct"] == [
        "FAKE correction 10",
        "FAKE correction 20",
        "FAKE correction 30",
    ]
