"""
sdks/python/sentinel_sdk/core.py
Sentinel Python SDK — Core Plugin
Auto-detects Flask/FastAPI/Django and reports errors to Agent Server
"""

import os
import sys
import traceback
import threading
from .monitor import SentinelMonitor


class Sentinel:
    """
    Thin client — catches errors and sends them to the Agent Server.
    All AI diagnosis, fixing, and alerting happens in the Agent Server.

    Usage:
        Sentinel(server_url="http://localhost:8000", app_name="MyApp").attach(app)
    """

    def __init__(
        self,
        server_url: str = "",
        app_name:   str = "MyApp",
        # Legacy params kept for backward compatibility
        api_key:          str = "",
        elastic_url:      str = "",
        elastic_password: str = "",
        email_to:         str = "",
        smtp_user:        str = "",
        smtp_pass:        str = "",
        whatsapp_to:      str = "",
        twilio_sid:       str = "",
        twilio_token:     str = "",
        **kwargs
    ):
        self.server_url = server_url or os.getenv("SENTINEL_URL", "http://localhost:8000")
        self.app_name   = app_name

        # If legacy keys passed — warn user
        if api_key or elastic_url:
            print("[Sentinel] ℹ️  API keys are now handled by the Agent Server.")
            print(f"[Sentinel] ℹ️  Set SENTINEL_URL to your running agent server.")

        self.monitor = SentinelMonitor(
            server_url = self.server_url,
            app_name   = self.app_name
        )
        self._install_global_hook()

    def attach(self, app) -> "Sentinel":
        framework = self._detect_framework(app)

        if   framework == "flask":   self._attach_flask(app)
        elif framework == "fastapi": self._attach_fastapi(app)
        elif framework == "django":  self._attach_django(app)
        elif framework == "wsgi":    return self._wrap_wsgi(app)

        self.monitor.start()
        print(f"\033[92m[Sentinel] ✅ Attached to {framework} — reporting to {self.server_url}\033[0m")
        return app

    def watch(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()

    @staticmethod
    def _detect_framework(app) -> str:
        module = type(app).__module__ or ""
        if "flask"     in module: return "flask"
        if "fastapi"   in module: return "fastapi"
        if "starlette" in module: return "fastapi"
        if "django"    in module: return "django"
        if callable(app):         return "wsgi"
        return "unknown"

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
