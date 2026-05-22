"""
agent_server/ai_healer.py
Sentinel — Gemini AI Healer with Elastic MCP context
"""

import json
import os
import logging

logger = logging.getLogger("sentinel.healer")


class AIHealer:
    def __init__(self, api_key: str = "", elastic_mcp=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.mcp     = elastic_mcp
        self._client = None
        self._init_gemini()

    def _init_gemini(self):
        if not self.api_key:
            logger.warning("[Sentinel] No GEMINI_API_KEY — rule-based fallback active")
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            logger.info("[Sentinel] Gemini 2.5 Pro ready")
        except ImportError:
            logger.warning("[Sentinel] pip install google-genai")

    def is_ready(self) -> bool:
        return self._client is not None

    def diagnose(self, error_context: dict) -> dict:
        if self._client:
            return self._gemini_diagnose(error_context)
        return self._rule_based_diagnose(error_context)

    def _gemini_diagnose(self, ctx: dict) -> dict:
        from google.genai import types

        error      = ctx.get("error",      "")
        error_type = ctx.get("error_type", "unknown")

        # ── Pull context from Elastic MCP ─────────────────────────
        mcp_context = ""
        if self.mcp:
            try:
                similar = self.mcp.search_similar_incidents(error, size=3)
                if similar:
                    mcp_context += "\n\nSimilar past incidents (via Elastic MCP):\n"
                    for s in similar:
                        mcp_context += f"  - Error     : {s.get('error','')[:80]}\n"
                        mcp_context += f"    Root Cause : {s.get('root_cause','')}\n"
                        mcp_context += f"    Fix Applied: {s.get('fix_applied','')}\n"

                fix_hist = self.mcp.get_fix_history(error_type, size=3)
                if fix_hist:
                    mcp_context += "\n\nPast successful fixes (via Elastic MCP):\n"
                    for f in fix_hist:
                        mcp_context += f"  - Fix    : {f.get('fix','')}\n"
            except Exception as e:
                logger.warning(f"[Sentinel] MCP context fetch failed: {e}")

        prompt = f"""You are Sentinel, an expert SRE AI agent.
You have access to Elasticsearch via MCP to learn from past incidents.

Analyze this error and respond ONLY in valid JSON — no markdown.

ERROR CONTEXT:
{json.dumps(ctx, indent=2, default=str)}
{mcp_context}

Return EXACTLY this JSON:
{{
  "root_cause":      "one clear sentence",
  "confidence":      88,
  "severity":        "critical|high|medium|low",
  "fix_type":        "restart|clear_cache|env_fix|dependency_fix|code_fix|rate_limit|manual",
  "fix_command":     "shell command or null",
  "explanation":     "2-3 technical sentences",
  "safe_to_autofix": true
}}"""

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=600
                )
            )
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"[Sentinel] Gemini error: {e}")
            return self._rule_based_diagnose(ctx)

    def _rule_based_diagnose(self, ctx: dict) -> dict:
        error_msg = str(ctx.get("error", "")).lower()
        tb        = str(ctx.get("traceback", "")).lower()
        combined  = error_msg + " " + tb

        rules = [
            (["connection refused", "econnrefused", "connectionerror"],
             "database", "high", "Database or service connection refused",
             "restart", "sudo systemctl restart postgresql"),
            (["timeout", "timed out"],
             "timeout", "high", "Request or query timed out",
             "clear_cache", None),
            (["memory", "memoryerror", "out of memory"],
             "memory", "critical", "Out of memory error",
             "restart", "sudo systemctl restart your-app"),
            (["no space left", "enospc"],
             "disk", "critical", "Disk full",
             "clear_cache", "find /var/log -name '*.log' -mtime +7 -delete"),
            (["importerror", "modulenotfounderror"],
             "dependency", "medium", "Missing dependency",
             "dependency_fix", "pip install -r requirements.txt"),
            (["rate limit", "429", "too many requests"],
             "rate_limit", "medium", "Rate limit exceeded",
             "rate_limit", None),
        ]

        for keywords, fix_type, severity, root_cause, fix_category, fix_command in rules:
            if any(k in combined for k in keywords):
                return {
                    "root_cause":      root_cause,
                    "confidence":      75,
                    "severity":        severity,
                    "fix_type":        fix_category,
                    "fix_command":     fix_command,
                    "explanation":     f"Rule-based: detected '{fix_type}' pattern.",
                    "safe_to_autofix": fix_command is not None and "restart" not in fix_category
                }

        return {
            "root_cause":      "Unknown error — manual investigation required",
            "confidence":      30,
            "severity":        "medium",
            "fix_type":        "manual",
            "fix_command":     None,
            "explanation":     "Could not automatically diagnose. Check logs manually.",
            "safe_to_autofix": False
        }
