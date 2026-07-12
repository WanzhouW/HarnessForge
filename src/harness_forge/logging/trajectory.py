from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .events import RunEvent


class TrajectoryWriter:
    """Synchronous JSONL writer used for reliable baseline traces."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def reset(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def append(self, event: RunEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def write_many(self, events: Iterable[RunEvent]) -> None:
        for event in events:
            self.append(event)
