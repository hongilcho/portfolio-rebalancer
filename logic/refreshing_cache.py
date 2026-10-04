"""Process-local snapshots: stale reads, single refresh, bounded failure retries."""
import threading
import time
from datetime import datetime, timezone


class MarketRefreshUnavailable(RuntimeError):
    pass


class RefreshingCache:
    def __init__(self, ttl, load, fetch, retry_seconds=30):
        self.ttl, self.load, self.fetch = ttl, load, fetch
        self.retry_seconds = retry_seconds
        self.value = None
        self.updated_at = 0.0
        self.loaded = False
        self.refreshing = False
        self.last_error = False
        self.retry_at = 0.0
        self.generation = 0
        self.revision = 0
        self.condition = threading.Condition()

    def _status(self):
        return {
            'updated_at': datetime.fromtimestamp(self.updated_at, timezone.utc).isoformat() if self.updated_at else None,
            'stale': not self.updated_at or time.time() - self.updated_at > self.ttl,
            'refreshing': self.refreshing,
            'refresh_failed': self.last_error,
        }

    def status(self):
        with self.condition:
            return self._status()

    def seed(self, value, updated_at):
        with self.condition:
            self.value, self.updated_at, self.loaded = value, updated_at, True

    def invalidate(self):
        with self.condition:
            self.revision += 1
            self.updated_at = 0.0
            self.retry_at = 0.0

    def get(self, force=False):
        with self.condition:
            if not self.loaded:
                try:
                    value, age = self.load()
                    if value is not None:
                        self.value, self.updated_at = value, time.time() - max(0, age)
                except Exception:
                    pass
                self.loaded = True
            stale = not self.updated_at or time.time() - self.updated_at > self.ttl
            if not force and self.value is not None:
                if stale and not self.refreshing and time.time() >= self.retry_at:
                    self.refreshing = True
                    threading.Thread(target=self._refresh, daemon=True).start()
                return self.value, self._status()
            if self.refreshing:
                # Forced/cold callers share the refresh already in progress.
                while self.refreshing:
                    self.condition.wait()
            elif force or time.time() >= self.retry_at:
                self.refreshing = True
                # Release condition while external IO runs.
                self.condition.release()
                try:
                    self._refresh()
                finally:
                    self.condition.acquire()
            if self.value is None or (force and self.last_error):
                raise MarketRefreshUnavailable('Market data refresh unavailable')
            return self.value, self._status()

    def _refresh(self):
        with self.condition:
            revision = self.revision
        try:
            value = self.fetch()
            if value is None:
                raise ValueError('No usable snapshot')
            with self.condition:
                if revision != self.revision:
                    self.last_error = True
                    return
                self.value, self.updated_at = value, time.time()
                self.last_error, self.retry_at = False, 0.0
                self.generation += 1
        except Exception:
            with self.condition:
                self.last_error, self.retry_at = True, time.time() + self.retry_seconds
        finally:
            with self.condition:
                self.refreshing = False
                self.condition.notify_all()
