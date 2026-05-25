"""
agent_server/monitor.py
Central Monitor — processes error reports from ALL language SDKs
"""

import uuid
import time
import threading
import logging
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger("sentinel.monitor")


class SentinelMonitor:
    def __init__(self, healer, fixer, notifier, mcp):
        self.healer   = healer
        self.fixer    = fixer
        self.notifier = notifier
        self.mcp      = mcp
        self._queue   = deque()
        self._seen    = {}
        self._lock    = threading.Lock()
        self._running = False
        self.incidents= deque(maxlen=200)

    def report(self, event: dict):
        """Called by /report endpoint — dedup then queue"""
        key = f"{event.get('error','')[:50]}{event.get('app_name','')}"
        now = time.time()
        with self._lock:
            if now - self._seen.get(key, 0) < 60:
                return  # deduplicate same error within 60s
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
                    self._process(event)
            time.sleep(0.3)

    def _process(self, event: dict):
        start      = time.time()
        error      = event.get("error",      "")
        error_type = event.get("error_type", "unknown")
        framework  = event.get("framework",  "unknown")
        language   = event.get("language",   "unknown")
        app_name   = event.get("app_name",   "unknown")

        # ── STAGE 1: Immediate alert ──────────────────────────────
        self.notifier.alert_detected(event)

        # ── STAGE 2: Store raw log via MCP ────────────────────────
        self.mcp.store_log(
            error     = error,
            framework = f"{language}/{framework}",
            severity  = "high",
            app_name  = app_name
        )

        # ── STAGE 3: Diagnose with Gemini + MCP context ───────────
        diagnosis = self.healer.diagnose(event)
        duration  = int((time.time() - start) * 1000)

        # ── STAGE 4: Apply safe auto-fix ─────────────────────────
        fix_result = self.fixer.execute(diagnosis, event)
        action     = (fix_result.get("action_taken")
                      or fix_result.get("skipped_reason", "no action"))

        # ── STAGE 5: Store incident via MCP ───────────────────────
        incident_id = self.mcp.store_incident(
            error       = error,
            error_type  = error_type,
            root_cause  = diagnosis.get("root_cause",  "Unknown"),
            fix_applied = action,
            confidence  = diagnosis.get("confidence",  0),
            severity    = diagnosis.get("severity",    "medium"),
            status      = "fixed" if fix_result.get("success") else "fix_failed",
            app_name    = app_name,
            language    = language,
            framework   = framework
        )

        # ── STAGE 6: Store fix result via MCP (agent learns) ──────
        self.mcp.store_fix_result(
            error_type  = error_type,
            fix         = action,
            success     = fix_result.get("success", False),
            duration_ms = duration,
            app_name    = app_name
        )

        # ── STAGE 7: Update incident status ───────────────────────
        if incident_id:
            self.mcp.update_incident_status(
                incident_id = incident_id,
                status      = "fixed" if fix_result.get("success") else "fix_failed",
                fix_applied = action
            )

        # ── STAGE 8: Build incident record ────────────────────────
        incident = {
            "id":         str(uuid.uuid4()),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "app_name":   app_name,
            "language":   language,
            "framework":  framework,
            "error":      error,
            "diagnosis":  diagnosis,
            "fix_result": fix_result,
            "elastic_id": incident_id
        }
        self.incidents.appendleft(incident)

        # ── STAGE 9: Post-fix alert ───────────────────────────────
        self.notifier.alert_resolved(incident)

        logger.info(f"[Sentinel] Processed {language}/{framework} — "
                    f"{diagnosis.get('severity','?')} — "
                    f"fix: {fix_result.get('success', False)}")
