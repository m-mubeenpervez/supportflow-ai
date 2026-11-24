"""Single-process admin login throttling.

Development implementation only. Multi-worker production
deployments require a shared store such as Redis.
"""

from collections import deque
from threading import Lock
from time import monotonic


MAX_FAILURES = 5
WINDOW_SECONDS = 300
MAX_TRACKED_CLIENTS = 10000


class AdminLoginThrottle:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.failures = {}
        self.inflight = {}

    def _prune(self, key, now):
        attempts = self.failures.get(key)

        if attempts is None:
            return None

        while attempts and now - attempts[0] >= WINDOW_SECONDS:
            attempts.popleft()

        if not attempts:
            self.failures.pop(key, None)
            return None

        return attempts

    def _prune_expired_clients(self, now):
        """Remove expired entries before evaluating capacity."""
        for client in list(self.failures):
            self._prune(client, now)

    def allowed(self, key: str) -> bool:
        now = self.clock()

        with self.lock:
            attempts = self._prune(key, now)

            if attempts is not None:
                return len(attempts) < MAX_FAILURES

            if len(self.failures) >= MAX_TRACKED_CLIENTS:
                self._prune_expired_clients(now)

            return len(self.failures) < MAX_TRACKED_CLIENTS

    def record_failure(self, key: str) -> None:
        now = self.clock()

        with self.lock:
            attempts = self._prune(key, now)

            if attempts is None:
                if len(self.failures) >= MAX_TRACKED_CLIENTS:
                    self._prune_expired_clients(now)

                if len(self.failures) >= MAX_TRACKED_CLIENTS:
                    # Refuse untracked clients at capacity.
                    # Callers must check allowed() before login.
                    return

                attempts = deque()
                self.failures[key] = attempts

            attempts.append(now)

    def begin_attempt(self, key: str) -> bool:
        """Atomically reserve capacity before authentication."""
        now = self.clock()

        with self.lock:
            attempts = self._prune(key, now)
            failed = len(attempts) if attempts else 0
            active = self.inflight.get(key, 0)

            if failed + active >= MAX_FAILURES:
                return False

            tracked = set(self.failures) | set(self.inflight)

            if key not in tracked and len(tracked) >= MAX_TRACKED_CLIENTS:
                self._prune_expired_clients(now)
                tracked = set(self.failures) | set(self.inflight)

                if len(tracked) >= MAX_TRACKED_CLIENTS:
                    return False

            self.inflight[key] = active + 1
            return True

    def finish_attempt(self, key: str, *, success: bool) -> None:
        """Release reservation, then record the result atomically."""
        now = self.clock()

        with self.lock:
            active = self.inflight.get(key, 0)

            if active <= 0:
                raise RuntimeError(
                    "No active login reservation for client"
                )

            if active == 1:
                self.inflight.pop(key, None)
            else:
                self.inflight[key] = active - 1

            if success:
                self.failures.pop(key, None)
            else:
                attempts = self._prune(key, now)

                if attempts is None:
                    from collections import deque
                    attempts = deque()
                    self.failures[key] = attempts

                attempts.append(now)

    def clear(self, key: str) -> None:
        with self.lock:
            self.failures.pop(key, None)

    def reset(self) -> None:
        """For isolated tests only."""
        with self.lock:
            self.failures.clear()


admin_login_throttle = AdminLoginThrottle()
