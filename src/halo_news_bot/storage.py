from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import QueueItem, dumps_pretty, utc_now_iso


DEFAULT_STATE = {
    "seen_fingerprints": [],
    "seen_titles": [],
    "published_by_day": {},
    "last_run_at": None,
    "stats": {"runs": 0, "fetched": 0, "queued": 0, "published": 0, "skipped": 0},
}


class JsonStorage:
    def __init__(self, queue_path: Path, state_path: Path, log_path: Path | None = None):
        self.queue_path = queue_path
        self.state_path = state_path
        self.log_path = log_path
        for path in (self.queue_path, self.state_path):
            path.parent.mkdir(parents=True, exist_ok=True)

    def load_queue(self) -> list[QueueItem]:
        if not self.queue_path.exists():
            return []
        raw = json.loads(self.queue_path.read_text(encoding="utf-8") or "[]")
        return [QueueItem.from_dict(item) for item in raw]

    def save_queue(self, items: list[QueueItem]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(dumps_pretty([item.to_dict() for item in items]), encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))
        data = json.loads(self.state_path.read_text(encoding="utf-8") or "{}")
        state = json.loads(json.dumps(DEFAULT_STATE))
        state.update(data)
        state["stats"] = {**DEFAULT_STATE["stats"], **data.get("stats", {})}
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(dumps_pretty(state), encoding="utf-8")

    def append_log(self, event: dict[str, Any]) -> None:
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if self.log_path.exists():
            try:
                existing = json.loads(self.log_path.read_text(encoding="utf-8") or "[]")
            except json.JSONDecodeError:
                existing = []
        event = {"at": utc_now_iso(), **event}
        existing.append(event)
        self.log_path.write_text(dumps_pretty(existing[-300:]), encoding="utf-8")

    def add_or_update_queue_item(self, item: QueueItem) -> bool:
        queue = self.load_queue()
        for index, existing in enumerate(queue):
            if existing.id == item.id:
                # Keep admin edits/status, refresh only if it is still pending/draft.
                if existing.status in {"pending", "draft", "failed"}:
                    item.status = existing.status
                    item.admin_note = existing.admin_note
                    queue[index] = item
                    self.save_queue(queue)
                return False
        queue.insert(0, item)
        self.save_queue(queue)
        return True

    def is_seen(self, fingerprint: str, normalized_title: str) -> bool:
        state = self.load_state()
        return fingerprint in set(state.get("seen_fingerprints", [])) or normalized_title in set(state.get("seen_titles", []))

    def mark_seen(self, fingerprint: str, normalized_title: str) -> None:
        state = self.load_state()
        fingerprints = list(dict.fromkeys([*state.get("seen_fingerprints", []), fingerprint]))[-2000:]
        titles = list(dict.fromkeys([*state.get("seen_titles", []), normalized_title]))[-2000:]
        state["seen_fingerprints"] = fingerprints
        state["seen_titles"] = titles
        self.save_state(state)

    def increment_stat(self, key: str, amount: int = 1) -> None:
        state = self.load_state()
        stats = state.setdefault("stats", {})
        stats[key] = int(stats.get(key, 0)) + amount
        self.save_state(state)

    def published_today_count(self) -> int:
        state = self.load_state()
        day = utc_now_iso()[:10]
        return int(state.get("published_by_day", {}).get(day, 0))

    def increment_published_today(self, amount: int = 1) -> None:
        state = self.load_state()
        day = utc_now_iso()[:10]
        by_day = state.setdefault("published_by_day", {})
        by_day[day] = int(by_day.get(day, 0)) + amount
        # keep small history
        if len(by_day) > 45:
            for old_day in sorted(by_day)[:-45]:
                by_day.pop(old_day, None)
        self.save_state(state)

    def status_counts(self) -> dict[str, int]:
        return dict(Counter(item.status for item in self.load_queue()))
