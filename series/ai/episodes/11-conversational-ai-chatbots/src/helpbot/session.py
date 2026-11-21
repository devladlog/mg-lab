"""A conversation's state, and a JSON-file store with an expiry. Production would use a database with a TTL."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,63}$")


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    messages: list[dict] = field(default_factory=list)   # the full history, never trimmed
    folded: int = 0                                      # messages[:folded] are in `summary` (or dropped in window mode)
    summary: str = ""
    state: str = "bot"                                   # "bot" or "handoff"
    handoff_reason: str | None = None
    tickets: list[dict] = field(default_factory=list)
    updated: float = field(default_factory=time.time)

    @property
    def active(self) -> list[dict]:
        return self.messages[self.folded:]

    @property
    def user_turns(self) -> int:
        return sum(1 for m in self.messages if m["role"] == "user")


class SessionStore:
    def __init__(self, directory, ttl_seconds: int = 3600):
        self.dir = Path(directory)
        self.ttl = ttl_seconds

    def _path(self, session_id: str) -> Path:
        if not ID_RE.match(session_id):
            raise ValueError("session id must be 6-64 chars of a-z, 0-9 and '-'")
        return self.dir / f"{session_id}.json"

    def save(self, s: Session) -> None:
        s.updated = time.time()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(s.id).write_text(json.dumps(asdict(s), ensure_ascii=False), encoding="utf-8")

    def load(self, session_id: str) -> Session | None:
        p = self._path(session_id)
        if not p.exists():
            return None
        s = Session(**json.loads(p.read_text(encoding="utf-8")))
        if time.time() - s.updated > self.ttl:
            p.unlink()
            return None
        return s

    def purge_expired(self) -> int:
        n = 0
        for p in self.dir.glob("*.json"):
            if time.time() - p.stat().st_mtime > self.ttl:
                p.unlink()
                n += 1
        return n
