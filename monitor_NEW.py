"""
SentinelMonitor — background thread that receives error reports,
fires IMMEDIATE alert, diagnoses, fixes, then fires RESOLVED alert.
NOW WITH: Full Elastic MCP integration (store, search, update)
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger("sentinel.monitor")


class ElasticMCP:
    """
    Elastic MCP Client — gives the AI agent tools to interact with Elasticsearch.
    The agent uses these tools to LEARN from past incidents, not just log them.
    """

    INDEX_INCIDENTS = "sentinel-incidents"
    INDEX_FIXES     = "sentinel-fixes"
    INDEX_LOGS      = "sentinel-logs"

    def __init__(self, elastic_url: str, elastic_user: str,
                 elastic_pass: str, app_name: str):
        self.app_name = app_name
        self._es      = None
        self._connect(elastic_url, elastic_user, elastic_pass)

    def _connect(self, url: str, user: str, password: str):
        if not url:
            logger.warning("[Sentinel MCP] No ELASTIC_URL — MCP tools disabled")
            return
        try:
            from elasticsearch import Elasticsearch
            client = Elasticsearch(
                url,
                basic_auth=(user, password),
                verify_certs=False
            )
            if client.ping():
                self._es = client
                self._ensure_indices()
                logger.info("[Sentinel MCP] ✅ Elastic MCP connected")
            else:
                logger.warning("[Sentinel MCP] Elastic ping failed")
        except Exception as e:
            logger.warning(f"[Sentinel MCP] Connection failed: {e}")

    def _ensure_indices(self):
        """Create indices if they don't exist"""
        indices = {
            self.INDEX_INCIDENTS: {
                "mappings": {
                    "properties": {
                        "timestamp":   {"type": "date"},
                        "app_name":    {"type": "keyword"},
                        "error":       {"type": "text"},
                        "error_type":  {"type": "keyword"},
                        "root_cause":  {"type": "text"},
                        "fix_applied": {"type": "text"},
                        "confidence":  {"type": "integer"},
                        "severity":    {"type": "keyword"},
                        "status":      {"type": "keyword"},
                        "fixed_at":    {"type": "date"}
                    }
                }
            },
            self.INDEX_FIXES: {
                "mappings": {
                    "properties": {
                        "timestamp":   {"type": "date"},
                        "app_name":    {"type": "keyword"},
                        "error_type":  {"type": "keyword"},
                        "fix":         {"type": "text"},
                        "success":     {"type": "boolean"},
                        "duration_ms": {"type": "integer"}
                    }
                }
            },
            self.INDEX_LOGS: {
                "mappings": {
                    "properties": {
                        "timestamp":   {"type": "date"},
                        "app_name":    {"type": "keyword"},
                        "error":       {"type": "text"},
                        "framework":   {"type": "keyword"},
                        "severity":    {"type": "keyword"}
                    }
                }
            }
        }
        for index, body in indices.items():
            try:
                if not self._es.indices.exists(index=index):
                    self._es.indices.create(index=index, body=body)
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._es is not None

    # ── MCP Tool 1: Store incident ────────────────────────────────
    def store_incident(self, error: str, error_type: str,
                       root_cause: str, fix_applied: str,
                       confidence: int, severity: str,
                       status: str) -> str:
        """MCP Tool — Store a diagnosed incident in Elasticsearch"""
        if not self._es:
            return ""
        try:
            doc = {
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "app_name":    self.app_name,
                "error":       error,
                "error_type":  error_type,
                "root_cause":  root_cause,
                "fix_applied": fix_applied,
                "confidence":  confidence,
                "severity":    severity,
                "status":      status
            }
            result = self._es.index(index=self.INDEX_INCIDENTS, document=doc)
            return result["_id"]
        except Exception as e:
            logger.warning(f"[Sentinel MCP] store_incident failed: {e}")
            return ""

    # ── MCP Tool 2: Update incident status ───────────────────────
    def update_incident_status(self, incident_id: str,
                                status: str, fix_applied: str = ""):
        """MCP Tool — Update incident after fix is applied"""
        if not self._es or not incident_id:
            return
        try:
            self._es.update(
                index=self.INDEX_INCIDENTS,
                id=incident_id,
                body={
                    "doc": {
                        "status":      status,
                        "fix_applied": fix_applied,
                        "fixed_at":    datetime.now(timezone.utc).isoformat()
                    }
                }
            )
        except Exception as e:
            logger.warning(f"[Sentinel MCP] update_incident_status failed: {e}")

    # ── MCP Tool 3: Search similar past incidents ─────────────────
    def search_similar_incidents(self, error: str, size: int = 3) -> list:
        """MCP Tool — Find similar past incidents using full-text search"""
        if not self._es:
            return []
        try:
            result = self._es.search(
                index=self.INDEX_INCIDENTS,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"match": {"error": error}},
                                {"term":  {"app_name": self.app_name}}
                            ]
                        }
                    },
                    "sort": [{"timestamp": {"order": "desc"}}],
                    "size": size
                }
            )
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"[Sentinel MCP] search_similar_incidents failed: {e}")
            return []

    # ── MCP Tool 4: Get fix history ───────────────────────────────
    def get_fix_history(self, error_type: str, size: int = 3) -> list:
        """MCP Tool — Get past successful fixes for learning"""
        if not self._es:
            return []
        try:
            result = self._es.search(
                index=self.INDEX_FIXES,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"error_type": error_type}},
                                {"term": {"app_name":   self.app_name}},
                                {"term": {"success":    True}}
                            ]
                        }
                    },
                    "sort": [{"timestamp": {"order": "desc"}}],
                    "size": size
                }
            )
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"[Sentinel MCP] get_fix_history failed: {e}")
            return []

    # ── MCP Tool 5: Store fix result ──────────────────────────────
    def store_fix_result(self, error_type: str, fix: str,
                          success: bool, duration_ms: int):
        """MCP Tool — Log what fix was applied and whether it worked"""
        if not self._es:
            return
        try:
            self._es.index(
                index=self.INDEX_FIXES,
                document={
                    "timestamp":   datetime.now(timezone.utc).isoformat(),
                    "app_name":    self.app_name,
                    "error_type":  error_type,
                    "fix":         fix,
                    "success":     success,
                    "duration_ms": duration_ms
                }
            )
        except Exception as e:
            logger.warning(f"[Sentinel MCP] store_fix_result failed: {e}")

    # ── MCP Tool 6: Raw log ───────────────────────────────────────
    def store_log(self, error: str, framework: str, severity: str):
        """MCP Tool — Store raw error log"""
        if not self._es:
            return
        try:
            self._es.index(
                index=self.INDEX_LOGS,
                document={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "app_name":  self.app_name,
                    "error":     error,
                    "framework": framework,
                    "severity":  severity
                }
            )
        except Exception as e:
            logger.warning(f"[Sentinel MCP] store_log failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────


class SentinelMonitor:
    def __init__(
        self,
        healer,
        fixer,
        notifier=None,
        elastic_url:  str = "",
        elastic_user: str = "elastic",
        elastic_pass: str = "",
        app_name:     str = "MyApp",
        on_fix=None,
        silent: bool = True,
    ):
        self.healer   = healer
        self.fixer    = fixer
        self.notifier = notifier
        self.on_fix   = on_fix
        self.silent   = silent

        # ── Boot Elastic MCP ──────────────────────────────────────
        self.mcp = ElasticMCP(
            elastic_url  = elastic_url  or os.getenv("ELASTIC_URL",      ""),
            elastic_user = elastic_user or "elastic",
            elastic_pass = elastic_pass or os.getenv("ELASTIC_PASSWORD",  ""),
            app_name     = app_name
        )

        # ── Inject MCP into healer so it can use context ──────────
        self.healer.mcp = self.mcp

        self._queue   = deque()
        self._seen    = {}
        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None
        self.incidents= deque(maxlen=100)

    # ── Public: called by middleware ──────────────────────────────
    def report_exception(self, error, traceback: str,
                          context: dict, framework: str):
        if error is None:
            return
        self._enqueue({
            "type":       "exception",
            "error":      str(error),
            "error_type": type(error).__name__,
            "traceback":  traceback,
            "context":    context,
            "framework":  framework,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    def report_http_error(self, path: str, method: str,
                           status: int, duration_ms: float, framework: str):
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

    # ── Queue + dedup ─────────────────────────────────────────────
    def _enqueue(self, event: dict):
        key = f"{event.get('error_type','')}{event.get('path','')}{event.get('error','')[:40]}"
        now = time.time()
        with self._lock:
            if now - self._seen.get(key, 0) < 60:
                return
            self._seen[key] = now
            self._queue.append(event)

    # ── Background worker ─────────────────────────────────────────
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
        import time as _time
        error      = event.get("error", "")
        error_type = event.get("error_type", "unknown")
        framework  = event.get("framework", "unknown")

        # ── STAGE 1: Immediate alert ──────────────────────────────
        if self.notifier:
            self.notifier.alert_detected(event)

        # ── STAGE 2: Store raw log via MCP ────────────────────────
        self.mcp.store_log(
            error     = error,
            framework = framework,
            severity  = "high"
        )

        # ── STAGE 3: Diagnose with Gemini + MCP context ───────────
        # (healer.mcp is already set — it queries Elastic internally)
        start     = _time.time()
        diagnosis = self.healer.diagnose(event)
        duration  = int((_time.time() - start) * 1000)

        # ── STAGE 4: Apply fix ────────────────────────────────────
        fix_result = self.fixer.execute(diagnosis, event)
        action     = fix_result.get("action_taken") or \
                     fix_result.get("skipped_reason", "no action")

        # ── STAGE 5: Store incident via MCP ───────────────────────
        incident_id = self.mcp.store_incident(
            error      = error,
            error_type = error_type,
            root_cause = diagnosis.get("root_cause",    "Unknown"),
            fix_applied= action,
            confidence = diagnosis.get("confidence",    0),
            severity   = diagnosis.get("severity",      "medium"),
            status     = "fixed" if fix_result.get("success") else "fix_failed"
        )

        # ── STAGE 6: Store fix result via MCP (agent learns) ──────
        self.mcp.store_fix_result(
            error_type  = error_type,
            fix         = action,
            success     = fix_result.get("success", False),
            duration_ms = duration
        )

        # ── STAGE 7: Update incident status via MCP ───────────────
        if incident_id:
            self.mcp.update_incident_status(
                incident_id = incident_id,
                status      = "fixed" if fix_result.get("success") else "fix_failed",
                fix_applied = action
            )

        # ── STAGE 8: Build incident record ────────────────────────
        incident = {
            "id":          str(uuid.uuid4()),
            "timestamp":   event.get("timestamp"),
            "framework":   framework,
            "event_type":  event.get("type"),
            "error":       error,
            "diagnosis":   diagnosis,
            "fix_result":  fix_result,
            "elastic_id":  incident_id
        }
        self.incidents.appendleft(incident)

        # ── STAGE 9: Post-fix alert ───────────────────────────────
        if self.notifier:
            self.notifier.alert_resolved(incident)

        # ── STAGE 10: Custom callback ─────────────────────────────
        if self.on_fix:
            try:
                self.on_fix(incident, fix_result)
            except Exception as e:
                logger.error(f"[Sentinel] on_fix callback error: {e}")


import os
