"""
agent_server/monitor.py
Sentinel — Background Monitor

FIXES APPLIED:
✅ Uses persistent SQLite queue (events survive restarts)
✅ Strong observability (structured logging every stage)
✅ Confidence routing passed to fixer
✅ Rollback info stored in incident record
"""

import os
import uuid
import time
import logging
import threading
from datetime import datetime, timezone
from collections import deque
from queue_store import PersistentQueue
from validator   import sanitize_report

logger = logging.getLogger("sentinel.monitor")


class SentinelMonitor:
    def __init__(self, healer, fixer, notifier, mcp):
        self.healer    = healer
        self.fixer     = fixer
        self.notifier  = notifier
        self.mcp       = mcp
        self._queue    = PersistentQueue()   # ✅ persistent SQLite queue
        self._seen     = {}
        self._lock     = threading.Lock()
        self._running  = False
        self.incidents = deque(maxlen=200)

    def report(self, event: dict):
        """Deduplicate then push to persistent queue"""
        # ✅ Sanitize before queuing
        event = sanitize_report(event)

        key = f"{event.get('error','')[:50]}{event.get('app_name','')}"
        now = time.time()
        with self._lock:
            if now - self._seen.get(key, 0) < 60:
                logger.info(f"[Monitor] Deduplicated event: {key[:40]}")
                return
            self._seen[key] = now

        event_id = self._queue.push(event)
        logger.info(f"[Monitor] Queued event #{event_id} from {event.get('app_name','?')}")

    def queue_size(self) -> int:
        return self._queue.size()

    def start(self):
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()
        logger.info("[Monitor] Background worker started")

    def stop(self):
        self._running = False

    def _worker(self):
        while self._running:
            event_id, event = self._queue.pop()
            if event_id and event:
                try:
                    self._process(event_id, event)
                except Exception as e:
                    logger.error(f"[Monitor] Processing error for event #{event_id}: {e}")
                    self._queue.mark_failed(event_id)
            else:
                time.sleep(0.3)

    def _process(self, event_id: int, event: dict):
        start      = time.time()
        error      = event.get("error",      "")
        error_type = event.get("error_type", "unknown")
        framework  = event.get("framework",  "unknown")
        language   = event.get("language",   "unknown")
        app_name   = event.get("app_name",   "unknown")

        logger.info(f"[Monitor] Processing #{event_id} — {language}/{framework} — {error[:50]}")

        try:
            # ── Stage 1: Immediate alert ──────────────────────────
            self.notifier.alert_detected(event)
            logger.info(f"[Monitor] #{event_id} Stage 1 ✅ — alert sent")

            # ── Stage 2: Store raw log via MCP ────────────────────
            self.mcp.store_log(
                error     = error,
                framework = f"{language}/{framework}",
                severity  = "high",
                app_name  = app_name
            )
            logger.info(f"[Monitor] #{event_id} Stage 2 ✅ — log stored in Elastic")

            # ── Stage 3: Diagnose with Gemini + MCP context ───────
            diagnosis = self.healer.diagnose(event)
            confidence= diagnosis.get("confidence", 0)
            severity  = diagnosis.get("severity",   "medium")
            logger.info(
                f"[Monitor] #{event_id} Stage 3 ✅ — "
                f"diagnosed: {diagnosis.get('root_cause','?')[:60]} "
                f"(confidence: {confidence}%)"
            )

            # ── Stage 4: Apply fix (confidence-routed) ────────────
            fix_result = self.fixer.execute(diagnosis, event)
            action     = (fix_result.get("action_taken")
                          or fix_result.get("skipped_reason", "no action"))
            logger.info(
                f"[Monitor] #{event_id} Stage 4 ✅ — "
                f"fix: {action[:60]} success={fix_result.get('success')}"
            )

            # ── Stage 5: Store incident via MCP ───────────────────
            incident_id = self.mcp.store_incident(
                error       = error,
                error_type  = error_type,
                root_cause  = diagnosis.get("root_cause",  "Unknown"),
                fix_applied = action,
                confidence  = confidence,
                severity    = severity,
                status      = "fixed" if fix_result.get("success") else "fix_failed",
                app_name    = app_name,
                language    = language,
                framework   = framework
            )
            logger.info(f"[Monitor] #{event_id} Stage 5 ✅ — incident stored (elastic id: {incident_id})")

            # ── Stage 6: Store fix result via MCP ─────────────────
            duration = int((time.time() - start) * 1000)
            self.mcp.store_fix_result(
                error_type  = error_type,
                fix         = action,
                success     = fix_result.get("success", False),
                duration_ms = duration,
                app_name    = app_name
            )
            logger.info(f"[Monitor] #{event_id} Stage 6 ✅ — fix result stored")

            # ── Stage 7: Update incident status via MCP ───────────
            if incident_id:
                self.mcp.update_incident_status(
                    incident_id = incident_id,
                    status      = "fixed" if fix_result.get("success") else "fix_failed",
                    fix_applied = action
                )
            logger.info(f"[Monitor] #{event_id} Stage 7 ✅ — incident status updated")

            # ── Stage 8: Build in-memory incident record ──────────
            incident = {
                "id":                 str(uuid.uuid4()),
                "event_id":           event_id,
                "timestamp":          datetime.now(timezone.utc).isoformat(),
                "app_name":           app_name,
                "language":           language,
                "framework":          framework,
                "error":              error,
                "diagnosis":          diagnosis,
                "fix_result":         fix_result,
                "elastic_id":         incident_id,
                "rollback_available": fix_result.get("rollback_available", False),
                "processing_ms":      int((time.time() - start) * 1000)
            }
            self.incidents.appendleft(incident)

            # ── Stage 9: Post-fix alert ───────────────────────────
            self.notifier.alert_resolved(incident)
            logger.info(f"[Monitor] #{event_id} Stage 9 ✅ — resolved alert sent")

            # ── Stage 10: Mark queue event done ───────────────────
            self._queue.mark_done(event_id)
            logger.info(
                f"[Monitor] #{event_id} ✅ COMPLETE — "
                f"total time: {incident['processing_ms']}ms"
            )

        except Exception as e:
            logger.error(f"[Monitor] #{event_id} ❌ FAILED — {e}")
            self._queue.mark_failed(event_id)
            raise