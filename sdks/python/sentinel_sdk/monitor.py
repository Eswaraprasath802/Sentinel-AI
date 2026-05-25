"""
sdks/python/sentinel_sdk/monitor.py
Sentinel Python SDK — Thin HTTP Client
Just sends error reports to the Agent Server — no AI logic here!
"""

import json
import time
import logging
import threading
import traceback
from datetime import datetime, timezone
from collections import deque
from urllib import request as urllib_request, error as urllib_error

logger = logging.getLogger("sentinel.sdk")


class SentinelMonitor:
    def __init__(self, server_url: str, app_name: str):
        self.server_url = server_url.rstrip("/")
        self.app_name   = app_name
        self._queue     = deque()
        self._seen      = {}
        self._lock      = threading.Lock()
        self._running   = False
        self._check_health()

    def _check_health(self):
        try:
            req = urllib_request.Request(f"{self.server_url}/health")
            with urllib_request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print(f"\033[92m[Sentinel] ✅ Agent Server connected at {self.server_url}\033[0m")
                    return
        except Exception:
            pass
        print(f"\033[93m[Sentinel] ⚠️  Agent Server not reachable at {self.server_url}\033[0m")

    def report_exception(self, error, tb: str, context: dict, framework: str):
        if error is None:
            return
        self._enqueue({
            "app_name":   self.app_name,
            "language":   "python",
            "framework":  framework,
            "error":      str(error),
            "error_type": type(error).__name__,
            "traceback":  tb,
            "endpoint":   context.get("path",   "unknown"),
            "method":     context.get("method", "unknown"),
            "timestamp":  datetime.now(timezone.utc).isoformat()
        })

    def report_http_error(self, path: str, method: str,
                           status: int, duration_ms: float, framework: str):
        self._enqueue({
            "app_name":    self.app_name,
            "language":    "python",
            "framework":   framework,
            "error":       f"HTTP {status} on {method} {path}",
            "error_type":  "HTTPError",
            "traceback":   "",
            "endpoint":    path,
            "method":      method,
            "timestamp":   datetime.now(timezone.utc).isoformat()
        })

    def _enqueue(self, event: dict):
        key = f"{event.get('error','')[:50]}{event.get('framework','')}"
        now = time.time()
        with self._lock:
            if now - self._seen.get(key, 0) < 60:
                return  # deduplicate within 60s
            self._seen[key] = now
            self._queue.append(event)

    def start(self):
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _worker(self):
        while self._running:
            if self._queue:
                with self._lock:
                    event = self._queue.popleft() if self._queue else None
                if event:
                    self._post(event)
            time.sleep(0.3)

    def _post(self, payload: dict):
        """Send error report to Agent Server via HTTP POST"""
        try:
            body = json.dumps(payload).encode("utf-8")
            req  = urllib_request.Request(
                f"{self.server_url}/report",
                data    = body,
                headers = {"Content-Type": "application/json"},
                method  = "POST"
            )
            with urllib_request.urlopen(req, timeout=3) as resp:
                pass  # fire and forget
        except Exception as e:
            logger.warning(f"[Sentinel] Could not reach agent server: {e}")
