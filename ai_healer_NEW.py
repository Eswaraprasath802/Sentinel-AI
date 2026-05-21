"""
AIHealer — sends error context to Gemini and gets back a diagnosis + fix plan.
NOW WITH: Elastic MCP context (similar incidents + fix history)
"""

import json
import os
import logging

logger = logging.getLogger("sentinel.healer")


class AIHealer:
    def __init__(self, api_key: str = "", elastic_mcp=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.mcp     = elastic_mcp   # ← Elastic MCP client injected here
        self._client = None
        self._init_gemini()

    def _init_gemini(self):
        if not self.api_key:
            logger.warning("[Sentinel] No GEMINI_API_KEY — AI diagnosis disabled (rule-based fallback active)")
            return
        try:
            # ── NEW Gemini SDK (google-genai) ─────────────────────
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            logger.info("[Sentinel] Gemini 2.5 Pro ready via google-genai SDK")
        except ImportError:
            logger.warning("[Sentinel] google-genai not installed — pip install google-genai")

    def diagnose(self, error_context: dict) -> dict:
        """
        Step 1 — Ask Elastic MCP for similar past incidents + fix history
        Step 2 — Send everything to Gemini 2.5 Pro for diagnosis
        """
        if self._client:
            return self._gemini_diagnose(error_context)
        return self._rule_based_diagnose(error_context)

    # ─── Gemini Diagnosis with MCP Context ───────────────────────
    def _gemini_diagnose(self, ctx: dict) -> dict:
        from google.genai import types

        error      = ctx.get("error", "")
        error_type = ctx.get("error_type", "unknown")

        # ── STEP 1: Pull context from Elastic MCP ─────────────────
        mcp_context = ""
        if self.mcp:
            try:
                # MCP Tool 1: Search similar past incidents
                similar = self.mcp.search_similar_incidents(error, size=3)
                if similar:
                    mcp_context += "\n\nSimilar past incidents from Elasticsearch (via MCP):\n"
                    for s in similar:
                        mcp_context += f"  - Error     : {s.get('error','')[:80]}\n"
                        mcp_context += f"    Root Cause : {s.get('root_cause','')}\n"
                        mcp_context += f"    Fix Applied: {s.get('fix_applied','')}\n"
                        mcp_context += f"    Status     : {s.get('status','')}\n"

                # MCP Tool 2: Get past successful fix history
                fix_hist = self.mcp.get_fix_history(error_type, size=3)
                if fix_hist:
                    mcp_context += "\n\nPast successful fixes from Elasticsearch (via MCP):\n"
                    for f in fix_hist:
                        mcp_context += f"  - Fix     : {f.get('fix','')}\n"
                        mcp_context += f"    Success : {f.get('success','')}\n"

            except Exception as e:
                logger.warning(f"[Sentinel] MCP context fetch failed: {e}")

        # ── STEP 2: Build prompt with MCP context ─────────────────
        prompt = f"""You are Sentinel, an expert SRE AI agent embedded in a web application.
You have access to Elasticsearch via MCP to learn from past incidents.

An error just occurred. Analyze it and respond with ONLY valid JSON — no markdown, no explanation outside the JSON.

ERROR CONTEXT:
{json.dumps(ctx, indent=2, default=str)}
{mcp_context}

Return this exact JSON:
{{
  "root_cause":      "one clear sentence",
  "confidence":      88,
  "severity":        "critical|high|medium|low",
  "fix_type":        "restart|clear_cache|env_fix|dependency_fix|code_fix|rate_limit|manual",
  "fix_command":     "shell command to fix, or null if not applicable",
  "explanation":     "2-3 sentences explaining what happened and why the fix works",
  "safe_to_autofix": true
}}

Rules:
- fix_command must be a safe, non-destructive shell command or null
- safe_to_autofix = false if the fix requires code changes or is risky
- If past incidents from MCP show a fix that worked before — prefer that fix
- Be specific about the root cause based on the error message and traceback"""

        try:
            # ── STEP 3: Call Gemini 2.5 Pro ───────────────────────
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

    # ─── Rule-Based Fallback ──────────────────────────────────────
    def _rule_based_diagnose(self, ctx: dict) -> dict:
        error_msg = str(ctx.get("error", "")).lower()
        tb        = str(ctx.get("traceback", "")).lower()
        combined  = error_msg + " " + tb

        rules = [
            (["connection refused", "econnrefused", "connectionerror"],
             "database", "high",
             "Database or external service connection refused",
             "restart",
             "sudo systemctl restart postgresql || sudo systemctl restart mysql"),

            (["timeout", "timed out", "deadlineexceeded"],
             "timeout", "high",
             "Service or database query timed out",
             "clear_cache",
             "echo 'Check slow queries and increase timeout limits'"),

            (["memory", "memoryerror", "out of memory", "oom"],
             "memory", "critical",
             "Out of memory — process running low on RAM",
             "restart",
             "sudo systemctl restart your-app"),

            (["disk", "no space left", "enospc"],
             "disk", "critical",
             "Disk full — no space left on device",
             "clear_cache",
             "find /var/log -name '*.log' -mtime +7 -delete && journalctl --vacuum-time=3d"),

            (["importerror", "modulenotfounderror", "cannot import"],
             "dependency", "medium",
             "Missing Python dependency",
             "dependency_fix",
             "pip install -r requirements.txt"),

            (["operationalerror", "db", "sqlite", "psycopg", "pymysql"],
             "database", "high",
             "Database operational error",
             "restart",
             "sudo systemctl restart postgresql"),

            (["500", "internal server error", "wsgi"],
             "app_crash", "high",
             "Application crashed with 500 error",
             "restart",
             "sudo systemctl restart gunicorn || pm2 restart all"),

            (["ratelimit", "rate limit", "429", "too many requests"],
             "rate_limit", "medium",
             "Rate limit exceeded on an external API",
             "rate_limit",
             None),
        ]

        for keywords, fix_type, severity, root_cause, fix_category, fix_command in rules:
            if any(k in combined for k in keywords):
                return {
                    "root_cause":      root_cause,
                    "confidence":      75,
                    "severity":        severity,
                    "fix_type":        fix_category,
                    "fix_command":     fix_command,
                    "explanation":     f"Detected '{fix_type}' pattern. Applied rule-based diagnosis.",
                    "safe_to_autofix": fix_command is not None and "restart" not in fix_category
                }

        return {
            "root_cause":      "Unknown error — manual investigation required",
            "confidence":      30,
            "severity":        "medium",
            "fix_type":        "manual",
            "fix_command":     None,
            "explanation":     "Could not automatically diagnose. Please check logs manually.",
            "safe_to_autofix": False
        }
