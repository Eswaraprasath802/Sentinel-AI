"""
Sentinel Core — auto-detects the framework and attaches the right middleware.
Supports: Flask, FastAPI, Django, plain WSGI/ASGI, or standalone use.
UPDATED: passes app_name to SentinelMonitor for Elastic MCP
"""

import os
import sys
import traceback
import threading
from .monitor  import SentinelMonitor
from .ai_healer import AIHealer
from .fixes    import AutoFixer
from .notifier import SentinelNotifier


class Sentinel:
    """
    Drop-in AI monitoring + auto-healing plugin.

    Minimal (terminal alerts only):
        Sentinel(api_key="GEMINI_KEY").attach(app)

    Full (terminal + email + whatsapp):
        Sentinel(
            api_key       = "GEMINI_KEY",
            email_to      = "you@example.com",
            email_from    = "alerts@example.com",
            smtp_user     = "alerts@example.com",
            smtp_pass     = "app_password",
            whatsapp_to   = "whatsapp:+919876543210",
            twilio_sid    = "ACxxxxx",
            twilio_token  = "xxxxx",
        ).attach(app)
    """

    def __init__(
        self,
        api_key: str = None,
        # Elastic MCP (required for hackathon)
        elastic_url:      str = None,
        elastic_user:     str = "elastic",
        elastic_password: str = None,
        # Email alerts
        email_to:   str = None,
        email_from: str = None,
        smtp_host:  str = "smtp.gmail.com",
        smtp_port:  int = 587,
        smtp_user:  str = None,
        smtp_pass:  str = None,
        # WhatsApp alerts
        whatsapp_to:  str = None,
        twilio_sid:   str = None,
        twilio_token: str = None,
        twilio_from:  str = "whatsapp:+14155238886",
        # General
        app_name: str  = "MyApp",
        silent:   bool = False,
        on_fix         = None,
    ):
        self.api_key  = api_key or os.getenv("GEMINI_API_KEY", "")
        self.app_name = app_name
        self.silent   = silent
        self.on_fix   = on_fix
        self._framework = None

        # ── Build notifier ────────────────────────────────────────
        self.notifier = SentinelNotifier(
            email_to     = email_to,
            email_from   = email_from,
            smtp_host    = smtp_host,
            smtp_port    = smtp_port,
            smtp_user    = smtp_user,
            smtp_pass    = smtp_pass,
            whatsapp_to  = whatsapp_to,
            twilio_sid   = twilio_sid,
            twilio_token = twilio_token,
            twilio_from  = twilio_from,
            app_name     = app_name,
        )

        # ── Build healer (MCP injected later by monitor) ──────────
        self.healer = AIHealer(api_key=self.api_key)
        self.fixer  = AutoFixer()

        # ── Build monitor with Elastic MCP ────────────────────────
        self.monitor = SentinelMonitor(
            healer       = self.healer,
            fixer        = self.fixer,
            notifier     = self.notifier,
            elastic_url  = elastic_url      or os.getenv("ELASTIC_URL",      ""),
            elastic_user = elastic_user,
            elastic_pass = elastic_password or os.getenv("ELASTIC_PASSWORD",  ""),
            app_name     = app_name,   # ← NEW: needed for MCP index filtering
            on_fix       = on_fix,
            silent       = silent,
        )

        self._install_global_hook()

    # ── Public API ────────────────────────────────────────────────
    def attach(self, app):
        framework = self._detect_framework(app)
        self._framework = framework

        if   framework == "flask":   self._attach_flask(app)
        elif framework == "fastapi": self._attach_fastapi(app)
        elif framework == "django":  self._attach_django(app)
        elif framework == "wsgi":    return self._wrap_wsgi(app)

        self.monitor.start()
        print(f"\033[92m[Sentinel] ✅ Attached to {framework} — Elastic MCP monitoring active\033[0m")
        return app

    def watch(self):
        self.monitor.start()
        print("\033[92m[Sentinel] ✅ Watching — Elastic MCP monitoring active\033[0m")

    def stop(self):
        self.monitor.stop()

    # ── Framework detection ───────────────────────────────────────
    @staticmethod
    def _detect_framework(app) -> str:
        module = type(app).__module__ or ""
        if "flask"     in module: return "flask"
        if "fastapi"   in module: return "fastapi"
        if "starlette" in module: return "fastapi"
        if "django"    in module: return "django"
        if callable(app):         return "wsgi"
        return "unknown"

    # ── Flask ─────────────────────────────────────────────────────
    def _attach_flask(self, app):
        monitor = self.monitor

        @app.before_request
        def _before():
            from flask import g
            import time
            g._sentinel_start = time.time()

        @app.after_request
        def _after(response):
            from flask import g, request
            import time
            ms = (time.time() - getattr(g, "_sentinel_start", time.time())) * 1000
            if response.status_code >= 500 or ms > 5000:
                monitor.report_http_error(
                    request.path, request.method,
                    response.status_code, ms, "flask"
                )
            return response

        @app.errorhandler(Exception)
        def _error(e):
            from flask import request, jsonify
            monitor.report_exception(
                e, traceback.format_exc(),
                {"path": request.path, "method": request.method}, "flask"
            )
            return jsonify({"error": "Internal Server Error",
                            "sentinel": "investigating"}), 500

    # ── FastAPI ───────────────────────────────────────────────────
    def _attach_fastapi(self, app):
        try:
            from starlette.middleware.base import BaseHTTPMiddleware
            from starlette.requests import Request
            import time
            monitor = self.monitor

            class _Middleware(BaseHTTPMiddleware):
                async def dispatch(self, request: Request, call_next):
                    start = time.time()
                    try:
                        resp = await call_next(request)
                        ms   = (time.time() - start) * 1000
                        if resp.status_code >= 500 or ms > 5000:
                            monitor.report_http_error(
                                request.url.path, request.method,
                                resp.status_code, ms, "fastapi"
                            )
                        return resp
                    except Exception as e:
                        monitor.report_exception(
                            e, traceback.format_exc(),
                            {"path": request.url.path}, "fastapi"
                        )
                        from starlette.responses import JSONResponse
                        return JSONResponse(
                            {"error": "Internal Server Error"}, status_code=500
                        )
            app.add_middleware(_Middleware)
        except ImportError:
            pass

    # ── Django ────────────────────────────────────────────────────
    def _attach_django(self, app):
        try:
            from django.core.signals import got_request_exception
            monitor = self.monitor

            def _handler(sender, request, **kwargs):
                monitor.report_exception(
                    sys.exc_info()[1], traceback.format_exc(),
                    {"path": getattr(request, "path", "?")}, "django"
                )
            got_request_exception.connect(_handler)
        except ImportError:
            pass

    # ── Generic WSGI ──────────────────────────────────────────────
    def _wrap_wsgi(self, app):
        monitor = self.monitor
        def _wsgi(environ, start_response):
            try:
                return app(environ, start_response)
            except Exception as e:
                monitor.report_exception(
                    e, traceback.format_exc(),
                    {"path": environ.get("PATH_INFO", "?")}, "wsgi"
                )
                raise
        return _wsgi

    # ── Global hook ───────────────────────────────────────────────
    def _install_global_hook(self):
        monitor = self.monitor
        _orig   = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            if not issubclass(exc_type, KeyboardInterrupt):
                monitor.report_exception(
                    exc_value,
                    "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
                    {"source": "global_hook"}, "python"
                )
            _orig(exc_type, exc_value, exc_tb)

        sys.excepthook = _hook

        if hasattr(threading, "excepthook"):
            _orig_t = threading.excepthook
            def _t_hook(args):
                if args.exc_type and not issubclass(args.exc_type, KeyboardInterrupt):
                    monitor.report_exception(
                        args.exc_value,
                        "".join(traceback.format_exception(
                            args.exc_type, args.exc_value, args.exc_traceback)),
                        {"source": "thread"}, "python"
                    )
                _orig_t(args)
            threading.excepthook = _t_hook
