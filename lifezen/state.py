"""Stato di esecuzione: evita pubblicazioni duplicate e traccia la cronologia."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


class State:
    """Piccolo store JSON su file, con scrittura atomica."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {"version": 1, "published": {}, "runs": []}
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(payload, dict):
            self.data.update(payload)
            self.data.setdefault("published", {})
            self.data.setdefault("runs", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
        ) as handle:
            handle.write(payload)
            tmp_name = handle.name
        os.replace(tmp_name, self.path)

    # ------------------------------------------------------------------
    def published_record(self, date: dt.date) -> Optional[dict]:
        return self.data["published"].get(date.isoformat())

    def is_published(self, date: dt.date) -> bool:
        record = self.published_record(date)
        return bool(record and record.get("media_id"))

    def record_publish(self, date: dt.date, payload: dict) -> None:
        self.data["published"][date.isoformat()] = {"at": _now_iso(), **payload}
        self.save()

    def record_run(self, payload: dict) -> None:
        runs: List[dict] = self.data.setdefault("runs", [])
        runs.insert(0, {"at": _now_iso(), **payload})
        del runs[40:]
        self.save()

    def stats(self) -> dict:
        published = self.data["published"]
        return {
            "pubblicati": len(published),
            "primo": min(published) if published else "—",
            "ultimo": max(published) if published else "—",
        }
