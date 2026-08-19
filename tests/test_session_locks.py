from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.services.session_locks import SessionLockManager


def test_different_sessions_can_run_in_parallel() -> None:
    manager = SessionLockManager()
    barrier = Barrier(2)

    def enter(session_id: str) -> str:
        with manager.acquire(session_id):
            barrier.wait(timeout=2)
            return session_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(enter, ["first-session", "second-session"]))

    assert results == ["first-session", "second-session"]
