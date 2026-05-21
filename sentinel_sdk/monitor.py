"""
SentinelMonitor — background thread that receives error reports,
fires IMMEDIATE alert, diagnoses, fixes, then fires RESOLVED alert.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from collections import deque

logger = logging.getLogger("sentinel.monitor")


class SentinelMonitor:
    def __init__(
        self,
        healer,
        fixer,
        notifier=None,
        elastic_url: str = "",
        elastic_user: str = "elastic",
        elastic_pass: str = "",
        on_fix=None,
        silent: bool = True,
    ):
        self.healer       = healer
        self.fixer        = fixer
        self.notifier     = notifier
        self.elastic_url  = elastic_url
        self.elastic_user = elastic_user
        self.elastic_pass = elastic_pass
        self.on_fix       = on_fix
        self.silent       = silent

        self._queue    = deque()
        self._seen     = {}
        self._lock     = threading.Lock()
        self._running  = False
        self._thread   = None
        self._es       = self._connect_elastic()
        self.incidents = deque(maxlen=100)

    # ── Elastic ───────────────────────────────────────────────────────────────

    def _connect_elastic(self):
        if not self.elastic_url:
            return None
        try:
            from elasticsearch import Elasticsearch
            client = Elasticsearch(
                self.elastic_url,
                basic_auth=(self.elastic_user, self.elastic_pass),
                verify_certs=False
            )
            if client.ping():
                return client
        except Exception as e:
            logger.warning(f"[Sentinel] Elastic not available: {e}")
        return None

    # ── Public: called by middleware ──────────────────────────────────────────

    def report_exception(self, error, traceback: str, context: dict, framework: str):
        if error is None:
            return
        import traceback as tb_mod
        self._enqueue({
            "type":       "exception",
            "error":      str(error),
            "error_type": type(error).__name__,
            "traceback":  traceback,
            "context":    context,
            "framework":  framework,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    def report_http_error(self, path: str, method: str, status: int, duration_ms: float, framework: str):
        self._enqueue({
            "type":        "http_error",
            "error":       f"HTTP {status} on {method} {path}",
            "path":        path,
            "method":      method,
            "status":      status,
            "duration_ms": duration_ms,
            "framework":   framework,
            "timestamp":   datetime.utcnow().isoformat(),
        })

    # ── Queue + dedup ─────────────────────────────────────────────────────────

    def _enqueue(self, event: dict):
        key = f"{event.get('error_type','')}{event.get('path','')}{event.get('error','')[:40]}"
        now = time.time()
        with self._lock:
            if now - self._seen.get(key, 0) < 60:
                return
            self._seen[key] = now
            self._queue.append(event)

    # ── Background worker ─────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _worker(self):
        while self._running:
            if self._queue:
                with self._lock:
                    event = self._queue.popleft() if self._queue else None
                if event:
                    self._process(event)
            time.sleep(0.5)

    def _process(self, event: dict):
        # ── STAGE 1: Immediate alert ──────────────────────────────────────────
        if self.notifier:
            self.notifier.alert_detected(event)

        # ── STAGE 2: Diagnose + Fix ───────────────────────────────────────────
        diagnosis  = self.healer.diagnose(event)
        fix_result = self.fixer.execute(diagnosis, event)

        incident = {
            "id":         str(uuid.uuid4()),
            "timestamp":  event.get("timestamp"),
            "framework":  event.get("framework"),
            "event_type": event.get("type"),
            "error":      event.get("error", "?"),
            "diagnosis":  diagnosis,
            "fix_result": fix_result,
        }
        self.incidents.appendleft(incident)

        # ── STAGE 3: Post-fix alert ───────────────────────────────────────────
        if self.notifier:
            self.notifier.alert_resolved(incident)

        # ── STAGE 4: Log to Elastic ───────────────────────────────────────────
        self._log_to_elastic(incident)

        # ── STAGE 5: Custom callback ──────────────────────────────────────────
        if self.on_fix:
            try:
                self.on_fix(incident, fix_result)
            except Exception as e:
                logger.error(f"[Sentinel] on_fix callback error: {e}")

    def _log_to_elastic(self, incident: dict):
        if not self._es:
            return
        try:
            self._es.index(index="sentinel-incidents", document=incident)
        except Exception as e:
            logger.warning(f"[Sentinel] Elastic log failed: {e}")
