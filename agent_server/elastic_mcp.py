"""
agent_server/elastic_mcp.py
Sentinel — Elastic MCP Client
All MCP tools for storing, searching, and learning from incidents
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("sentinel.mcp")


class ElasticMCP:
    INDEX_INCIDENTS = "sentinel-incidents"
    INDEX_FIXES     = "sentinel-fixes"
    INDEX_LOGS      = "sentinel-logs"

    def __init__(self, elastic_url: str, elastic_user: str,
                 elastic_pass: str, app_name: str = "sentinel"):
        self.app_name = app_name
        self._es      = None
        self._connect(elastic_url, elastic_user, elastic_pass)

    def _connect(self, url, user, password):
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
        indices = {
            self.INDEX_INCIDENTS: {
                "mappings": {
                    "properties": {
                        "timestamp":   {"type": "date"},
                        "app_name":    {"type": "keyword"},
                        "language":    {"type": "keyword"},
                        "framework":   {"type": "keyword"},
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
                        "timestamp": {"type": "date"},
                        "app_name":  {"type": "keyword"},
                        "language":  {"type": "keyword"},
                        "framework": {"type": "keyword"},
                        "error":     {"type": "text"},
                        "severity":  {"type": "keyword"}
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

    # ── MCP Tool 1: Store raw log ─────────────────────────────────
    def store_log(self, error: str, framework: str,
                  severity: str, app_name: str = ""):
        if not self._es:
            return
        try:
            lang, fw = (framework.split("/") + ["unknown"])[:2]
            self._es.index(index=self.INDEX_LOGS, document={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "app_name":  app_name or self.app_name,
                "language":  lang,
                "framework": fw,
                "error":     error,
                "severity":  severity
            })
        except Exception as e:
            logger.warning(f"[MCP] store_log failed: {e}")

    # ── MCP Tool 2: Store incident ────────────────────────────────
    def store_incident(self, error: str, error_type: str,
                       root_cause: str, fix_applied: str,
                       confidence: int, severity: str,
                       status: str, app_name: str = "",
                       language: str = "", framework: str = "") -> str:
        if not self._es:
            return ""
        try:
            result = self._es.index(index=self.INDEX_INCIDENTS, document={
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "app_name":    app_name  or self.app_name,
                "language":    language,
                "framework":   framework,
                "error":       error,
                "error_type":  error_type,
                "root_cause":  root_cause,
                "fix_applied": fix_applied,
                "confidence":  confidence,
                "severity":    severity,
                "status":      status
            })
            return result["_id"]
        except Exception as e:
            logger.warning(f"[MCP] store_incident failed: {e}")
            return ""

    # ── MCP Tool 3: Update incident status ────────────────────────
    def update_incident_status(self, incident_id: str,
                                status: str, fix_applied: str = ""):
        if not self._es or not incident_id:
            return
        try:
            self._es.update(
                index=self.INDEX_INCIDENTS,
                id=incident_id,
                body={"doc": {
                    "status":      status,
                    "fix_applied": fix_applied,
                    "fixed_at":    datetime.now(timezone.utc).isoformat()
                }}
            )
        except Exception as e:
            logger.warning(f"[MCP] update_incident_status failed: {e}")

    # ── MCP Tool 4: Search similar incidents ──────────────────────
    def search_similar_incidents(self, error: str, size: int = 3) -> list:
        if not self._es:
            return []
        try:
            result = self._es.search(
                index=self.INDEX_INCIDENTS,
                body={
                    "query": {"match": {"error": error}},
                    "sort":  [{"timestamp": {"order": "desc"}}],
                    "size":  size
                }
            )
            return [h["_source"] for h in result["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"[MCP] search_similar_incidents failed: {e}")
            return []

    # ── MCP Tool 5: Get fix history ───────────────────────────────
    def get_fix_history(self, error_type: str, size: int = 3) -> list:
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
                                {"term": {"success":    True}}
                            ]
                        }
                    },
                    "sort": [{"timestamp": {"order": "desc"}}],
                    "size": size
                }
            )
            return [h["_source"] for h in result["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"[MCP] get_fix_history failed: {e}")
            return []

    # ── MCP Tool 6: Store fix result ──────────────────────────────
    def store_fix_result(self, error_type: str, fix: str,
                          success: bool, duration_ms: int,
                          app_name: str = ""):
        if not self._es:
            return
        try:
            self._es.index(index=self.INDEX_FIXES, document={
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "app_name":    app_name or self.app_name,
                "error_type":  error_type,
                "fix":         fix,
                "success":     success,
                "duration_ms": duration_ms
            })
        except Exception as e:
            logger.warning(f"[MCP] store_fix_result failed: {e}")

    # ── MCP Tool 7: Get stats ─────────────────────────────────────
    def get_stats(self) -> dict:
        if not self._es:
            return {}
        try:
            result = self._es.search(
                index=self.INDEX_INCIDENTS,
                body={
                    "aggs": {
                        "by_status":   {"terms": {"field": "status"}},
                        "by_severity": {"terms": {"field": "severity"}},
                        "by_language": {"terms": {"field": "language"}}
                    },
                    "size": 0
                }
            )
            aggs = result.get("aggregations", {})
            return {
                "total": result["hits"]["total"]["value"],
                "by_status":   {b["key"]: b["doc_count"] for b in aggs.get("by_status",   {}).get("buckets", [])},
                "by_severity": {b["key"]: b["doc_count"] for b in aggs.get("by_severity", {}).get("buckets", [])},
                "by_language": {b["key"]: b["doc_count"] for b in aggs.get("by_language", {}).get("buckets", [])},
            }
        except Exception as e:
            logger.warning(f"[MCP] get_stats failed: {e}")
            return {}
