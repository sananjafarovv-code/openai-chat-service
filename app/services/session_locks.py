from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock


class _LockEntry:
    def __init__(self) -> None:
        self.lock = Lock()
        self.users = 0


class SessionLockManager:
    """Serializes messages per session inside a single application process."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._entries: dict[str, _LockEntry] = {}

    @contextmanager
    def acquire(self, session_id: str) -> Iterator[None]:
        with self._guard:
            entry = self._entries.setdefault(session_id, _LockEntry())
            entry.users += 1

        entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            with self._guard:
                entry.users -= 1
                if entry.users == 0:
                    self._entries.pop(session_id, None)
