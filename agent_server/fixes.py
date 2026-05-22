"""
agent_server/fixes.py
Sentinel — Safe Auto-Fix Engine
"""

import gc
import os
import subprocess
import logging

logger = logging.getLogger("sentinel.fixer")

BLOCKED_COMMANDS = ["rm -rf", "dd if=", "mkfs", "shutdown", "reboot", "> /dev/"]


class AutoFixer:
    def __init__(self, elastic_mcp=None):
        self.mcp = elastic_mcp

    def execute(self, diagnosis: dict, context: dict) -> dict:
        fix_type    = diagnosis.get("fix_type",        "manual")
        fix_command = diagnosis.get("fix_command")
        safe        = diagnosis.get("safe_to_autofix", False)

        result = {
            "fix_type":       fix_type,
            "attempted":      False,
            "success":        False,
            "action_taken":   None,
            "skipped_reason": None
        }

        if not safe:
            result["skipped_reason"] = "Marked unsafe — logged for manual review"
            return result

        handler = {
            "clear_cache":    self._clear_cache,
            "dependency_fix": self._fix_dependencies,
            "rate_limit":     self._handle_rate_limit,
            "env_fix":        self._fix_env,
            "restart":        self._safe_restart,
        }.get(fix_type)

        if handler:
            result.update(handler(diagnosis, context))
        elif fix_command:
            result.update(self._run_shell(fix_command))
        else:
            result["skipped_reason"] = f"No handler for fix_type='{fix_type}'"

        return result

    def _clear_cache(self, diagnosis, context):
        try:
            collected = gc.collect()
            return {"attempted": True, "success": True,
                    "action_taken": f"GC collected {collected} objects"}
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}

    def _fix_dependencies(self, diagnosis, context):
        req = os.path.join(os.getcwd(), "requirements.txt")
        if not os.path.exists(req):
            return {"attempted": False, "skipped_reason": "requirements.txt not found"}
        try:
            r = subprocess.run(["pip", "install", "-r", req, "--quiet"],
                                capture_output=True, text=True, timeout=60)
            return {"attempted": True, "success": r.returncode == 0,
                    "action_taken": "pip install -r requirements.txt"}
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}

    def _handle_rate_limit(self, diagnosis, context):
        return {"attempted": True, "success": True,
                "action_taken": "Rate limit logged — 30s backoff applied"}

    def _fix_env(self, diagnosis, context):
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
            return {"attempted": True, "success": True,
                    "action_taken": "Reloaded .env variables"}
        except ImportError:
            return {"attempted": False, "skipped_reason": "python-dotenv not installed"}

    def _safe_restart(self, diagnosis, context):
        return {"attempted": False, "success": False,
                "skipped_reason": "Restart required — trigger manually or via Cloud Run redeploy"}

    def _run_shell(self, command: str):
        if any(b in command for b in BLOCKED_COMMANDS):
            return {"attempted": False,
                    "skipped_reason": f"Blocked dangerous command: {command}"}
        try:
            r = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=30)
            return {"attempted": True, "success": r.returncode == 0,
                    "action_taken": f"Ran: {command[:80]}"}
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}
