"""
AIHealer — sends error context to Gemini and gets back a diagnosis + fix plan.
"""

import json
import os
import logging

logger = logging.getLogger("sentinel.healer")


class AIHealer:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = None
        self._init_gemini()

    def _init_gemini(self):
        if not self.api_key:
            logger.warning("[Sentinel] No GEMINI_API_KEY — AI diagnosis disabled (rule-based fallback active)")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel("gemini-1.5-pro")
        except ImportError:
            logger.warning("[Sentinel] google-generativeai not installed — pip install google-generativeai")

    def diagnose(self, error_context: dict) -> dict:
        """
        Takes an error context dict and returns:
        {
            "root_cause": str,
            "confidence": int,
            "fix_type": str,          # "restart" | "clear_cache" | "env_fix" | "code_fix" | "manual"
            "fix_command": str|None,  # shell command to run, if applicable
            "explanation": str,
            "severity": str           # "critical" | "high" | "medium" | "low"
        }
        """
        if self._model:
            return self._gemini_diagnose(error_context)
        return self._rule_based_diagnose(error_context)

    def _gemini_diagnose(self, ctx: dict) -> dict:
        prompt = f"""You are Sentinel, an expert SRE AI agent embedded in a web application.

An error just occurred. Analyze it and respond with ONLY valid JSON — no markdown, no explanation outside the JSON.

ERROR CONTEXT:
{json.dumps(ctx, indent=2, default=str)}

Return this exact JSON:
{{
  "root_cause": "one clear sentence",
  "confidence": 88,
  "severity": "critical|high|medium|low",
  "fix_type": "restart|clear_cache|env_fix|dependency_fix|code_fix|rate_limit|manual",
  "fix_command": "shell command to fix, or null if not applicable",
  "explanation": "2-3 sentences explaining what happened and why the fix works",
  "safe_to_autofix": true
}}

Rules:
- fix_command must be a safe, non-destructive shell command or null
- safe_to_autofix = false if the fix requires code changes or is risky
- Be specific about the root cause based on the error message and traceback"""

        try:
            response = self._model.generate_content(prompt)
            text = response.text.strip()
            # Strip markdown fences if present
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"[Sentinel] Gemini error: {e}")
            return self._rule_based_diagnose(ctx)

    def _rule_based_diagnose(self, ctx: dict) -> dict:
        """Fallback rule-based diagnosis when Gemini is unavailable."""
        error_msg = str(ctx.get("error", "")).lower()
        tb        = str(ctx.get("traceback", "")).lower()
        combined  = error_msg + " " + tb

        rules = [
            (["connection refused", "econnrefused", "connectionerror"],
             "database", "high",
             "Database or external service connection refused",
             "restart", "sudo systemctl restart postgresql || sudo systemctl restart mysql"),

            (["timeout", "timed out", "deadlineexceeded"],
             "timeout", "high",
             "Service or database query timed out",
             "clear_cache", "echo 'Check slow queries and increase timeout limits'"),

            (["memory", "memoryerror", "out of memory", "oom"],
             "memory", "critical",
             "Out of memory — process running low on RAM",
             "restart", "sudo systemctl restart your-app"),

            (["disk", "no space left", "enospc"],
             "disk", "critical",
             "Disk full — no space left on device",
             "clear_cache", "find /var/log -name '*.log' -mtime +7 -delete && journalctl --vacuum-time=3d"),

            (["importerror", "modulenotfounderror", "cannot import"],
             "dependency", "medium",
             "Missing Python dependency",
             "dependency_fix", "pip install -r requirements.txt"),

            (["operationalerror", "db", "sqlite", "psycopg", "pymysql"],
             "database", "high",
             "Database operational error",
             "restart", "sudo systemctl restart postgresql"),

            (["500", "internal server error", "wsgi"],
             "app_crash", "high",
             "Application crashed with 500 error",
             "restart", "sudo systemctl restart gunicorn || pm2 restart all"),

            (["ratelimit", "rate limit", "429", "too many requests"],
             "rate_limit", "medium",
             "Rate limit exceeded on an external API",
             "rate_limit", None),
        ]

        for keywords, fix_type, severity, root_cause, fix_category, fix_command in rules:
            if any(k in combined for k in keywords):
                return {
                    "root_cause": root_cause,
                    "confidence": 75,
                    "severity": severity,
                    "fix_type": fix_category,
                    "fix_command": fix_command,
                    "explanation": f"Detected '{fix_type}' pattern in error. Applied rule-based diagnosis.",
                    "safe_to_autofix": fix_command is not None and "restart" not in fix_category
                }

        return {
            "root_cause": "Unknown error — manual investigation required",
            "confidence": 30,
            "severity": "medium",
            "fix_type": "manual",
            "fix_command": None,
            "explanation": "Could not automatically diagnose this error. Please check logs manually.",
            "safe_to_autofix": False
        }
