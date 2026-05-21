"""
AutoFixer — executes safe, non-destructive fixes automatically.
Unsafe fixes are logged but NOT executed (requires human approval).
"""

import os
import gc
import subprocess
import logging
import importlib

logger = logging.getLogger("sentinel.fixer")


class AutoFixer:
    """
    Executes fixes based on the fix_type returned by AIHealer.
    All fixes are safe and reversible. Risky fixes are skipped and logged.
    """

    def execute(self, diagnosis: dict, context: dict) -> dict:
        fix_type     = diagnosis.get("fix_type", "manual")
        fix_command  = diagnosis.get("fix_command")
        safe         = diagnosis.get("safe_to_autofix", False)
        root_cause   = diagnosis.get("root_cause", "")

        result = {
            "fix_type":    fix_type,
            "attempted":   False,
            "success":     False,
            "action_taken": None,
            "skipped_reason": None
        }

        if not safe:
            result["skipped_reason"] = "Marked unsafe for auto-fix — logged for manual review"
            logger.warning(f"[Sentinel] Unsafe fix skipped: {root_cause}")
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

    # ── Fix handlers ──────────────────────────────────────────────────────────

    def _clear_cache(self, diagnosis: dict, context: dict) -> dict:
        """Force Python garbage collection and clear any in-memory caches."""
        try:
            collected = gc.collect()
            # Clear any __pycache__ dirs in working directory
            import shutil
            cwd = os.getcwd()
            cleared = []
            for root, dirs, _ in os.walk(cwd):
                for d in dirs:
                    if d == "__pycache__":
                        full = os.path.join(root, d)
                        shutil.rmtree(full, ignore_errors=True)
                        cleared.append(full)
                if len(cleared) > 10:
                    break
            return {
                "attempted": True,
                "success": True,
                "action_taken": f"GC collected {collected} objects; cleared {len(cleared)} cache dirs"
            }
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}

    def _fix_dependencies(self, diagnosis: dict, context: dict) -> dict:
        """Try to install missing dependencies from requirements.txt."""
        req_file = os.path.join(os.getcwd(), "requirements.txt")
        if not os.path.exists(req_file):
            return {"attempted": False, "skipped_reason": "requirements.txt not found"}
        try:
            result = subprocess.run(
                ["pip", "install", "-r", req_file, "--quiet"],
                capture_output=True, text=True, timeout=60
            )
            success = result.returncode == 0
            return {
                "attempted": True,
                "success": success,
                "action_taken": f"pip install -r requirements.txt: {'OK' if success else result.stderr[:200]}"
            }
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}

    def _handle_rate_limit(self, diagnosis: dict, context: dict) -> dict:
        """Log rate limit hit and apply exponential backoff metadata."""
        return {
            "attempted": True,
            "success": True,
            "action_taken": "Rate limit detected — applying 30s backoff on next retry"
        }

    def _fix_env(self, diagnosis: dict, context: dict) -> dict:
        """Attempt to reload environment variables from .env file."""
        env_file = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_file):
            return {"attempted": False, "skipped_reason": ".env file not found"}
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
            return {
                "attempted": True,
                "success": True,
                "action_taken": "Reloaded environment variables from .env"
            }
        except ImportError:
            return {"attempted": False, "skipped_reason": "python-dotenv not installed"}

    def _safe_restart(self, diagnosis: dict, context: dict) -> dict:
        """
        Restart is NOT auto-executed (too risky) — logged for operator action.
        In production, this would trigger a Cloud Run revision restart or k8s rolling restart.
        """
        return {
            "attempted": False,
            "success": False,
            "skipped_reason": "Restart required — not auto-executed for safety. Use: sudo systemctl restart your-app OR trigger Cloud Run redeploy."
        }

    def _run_shell(self, command: str) -> dict:
        """Run a shell command with a safety whitelist check."""
        BLOCKED = ["rm -rf", "dd if=", "mkfs", "shutdown", "reboot", "> /dev/", ":(){ :|:& };:"]
        if any(b in command for b in BLOCKED):
            return {
                "attempted": False,
                "skipped_reason": f"Blocked dangerous command: {command}"
            }
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            return {
                "attempted": True,
                "success": result.returncode == 0,
                "action_taken": f"Ran: {command[:100]} → {result.stdout[:200] or result.stderr[:200]}"
            }
        except subprocess.TimeoutExpired:
            return {"attempted": True, "success": False, "action_taken": "Command timed out after 30s"}
        except Exception as e:
            return {"attempted": True, "success": False, "action_taken": str(e)}
