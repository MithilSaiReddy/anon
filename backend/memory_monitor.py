import logging
import threading
import time

import psutil


logger = logging.getLogger(__name__)

WARN_THRESHOLD_MB = 500


class MemoryThresholdExceeded(Exception):
    pass


class MemoryMonitor:
    def __init__(self, limit_mb=600, poll_interval=0.5):
        self.limit = limit_mb * 1024 * 1024
        self.warn_limit = WARN_THRESHOLD_MB * 1024 * 1024
        self.interval = poll_interval
        self._running = False
        self._thread = None
        self._proc = psutil.Process()
        self.exceeded = False
        self._warned = False

    def __enter__(self):
        self.exceeded = False
        self._running = True
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def check(self):
        if self.exceeded:
            raise MemoryThresholdExceeded(
                "File Too Large — processing exceeded memory limit"
            )

    def _poll(self):
        while self._running:
            try:
                rss = self._proc.memory_info().rss
                if rss > self.limit:
                    logger.error("Memory limit exceeded: %.0f MB", rss / (1024 * 1024))
                    self.exceeded = True
                    break
                if rss > self.warn_limit and not self._warned:
                    logger.warning("Memory approaching limit: %.0f / %d MB", rss / (1024 * 1024), self.limit / (1024 * 1024))
                    self._warned = True
            except Exception:
                break
            time.sleep(self.interval)
