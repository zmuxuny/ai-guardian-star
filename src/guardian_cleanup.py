"""Periodic retention cleanup with an explicit clock-trust gate.

``cleanup_expired`` refuses to delete anything unless the caller asserts that
the wall clock is trustworthy.  On the board that means: the system year is
plausible AND systemd reports NTP synchronization.  Without both, the
scheduler only records a skip reason — media is never removed on a guess.
"""

from datetime import datetime
import subprocess
import threading
import time


def system_clock_trusted(now=None):
    """True only when the year is plausible and NTP reports synchronization."""
    now = time.time() if now is None else now
    try:
        if not 2020 <= datetime.fromtimestamp(now).year <= 2100:
            return False
    except (OverflowError, OSError, ValueError):
        return False
    try:
        done = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and done.stdout.strip() == "yes"


class CleanupScheduler:
    """One daemon thread; failures are recorded, never raised into the service."""

    def __init__(self, store, interval_seconds, trusted_probe=system_clock_trusted,
                 monotonic=time.monotonic, clock=time.time):
        self.store = store
        self.interval_seconds = max(10, int(interval_seconds))
        self._trusted_probe = trusted_probe
        self._monotonic = monotonic
        # Injectable wall clock so retention can be verified offline by
        # advancing simulated time instead of waiting 24 real hours.
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker = None
        self._runs = 0
        self._last_summary = None
        self._last_error = None

    def start(self):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return True
            self._stop.clear()
            self._worker = threading.Thread(target=self._run,
                                            name="guardian-cleanup", daemon=True)
            worker = self._worker
        try:
            worker.start()
        except Exception:
            with self._lock:
                self._worker = None
            return False
        return True

    def stop(self, timeout=5.0):
        with self._lock:
            worker = self._worker
            if worker is None:
                return True
            self._stop.set()
            self._wake.set()
        worker.join(float(timeout))
        with self._lock:
            alive = worker.is_alive()
            if not alive:
                self._worker = None
            return not alive

    def run_once(self, dry_run=False):
        """One guarded cleanup pass; returns the summary dictionary."""
        from guardian_storage import cleanup_expired
        trusted = bool(self._trusted_probe())
        try:
            summary = cleanup_expired(self.store, now=self._clock(),
                                      time_trusted=trusted, dry_run=dry_run)
        except Exception as exc:
            summary = {"error": type(exc).__name__}
        with self._lock:
            self._runs += 1
            self._last_summary = summary
            if summary.get("error"):
                self._last_error = summary["error"]
        return summary

    def status(self):
        with self._lock:
            return {"worker_alive": self._worker is not None and self._worker.is_alive(),
                    "interval_seconds": self.interval_seconds,
                    "runs": self._runs,
                    "last_summary": self._last_summary,
                    "last_error": self._last_error}

    def _run(self):
        next_due = self._monotonic() + self.interval_seconds
        while not self._stop.is_set():
            now = self._monotonic()
            if now >= next_due:
                self.run_once()
                next_due = self._monotonic() + self.interval_seconds
            self._wake.wait(min(1.0, max(0.05, next_due - self._monotonic())))
            self._wake.clear()
