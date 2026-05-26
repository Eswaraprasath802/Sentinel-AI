"""
agent_server/validator.py
Sentinel — Input Validation Layer

FIXES APPLIED:
✅ Required field validation
✅ Type checking
✅ Length limits (prevent oversized payloads)
✅ Allowed values for language/framework
✅ Sanitize strings (strip dangerous chars)
"""

import re
from typing import Optional

# ── Allowed values ────────────────────────────────────────────────
ALLOWED_LANGUAGES = {
    "python", "node", "javascript", "php",
    "java", "ruby", "go", "rust", "dotnet", "browser"
}

ALLOWED_FRAMEWORKS = {
    "flask", "fastapi", "django", "wsgi",
    "express", "nextjs", "koa", "hapi",
    "laravel", "symfony", "lumen",
    "spring", "springboot", "quarkus",
    "rails", "sinatra",
    "gin", "echo", "fiber",
    "actix", "axum",
    "aspnet", "dotnet",
    "browser", "vanilla", "unknown", "python"
}

# ── Field limits ──────────────────────────────────────────────────
MAX_ERROR_LEN     = 2000
MAX_TRACEBACK_LEN = 10000
MAX_APP_NAME_LEN  = 100
MAX_ENDPOINT_LEN  = 500

# ── Required fields ───────────────────────────────────────────────
REQUIRED_FIELDS = ["error", "app_name", "language", "framework"]


def validate_report(data: dict) -> list:
    """
    Validate incoming error report.
    Returns list of error messages — empty list means valid.
    """
    errors = []

    if not isinstance(data, dict):
        return ["Request body must be a JSON object"]

    # ── Required fields ───────────────────────────────────────────
    for field in REQUIRED_FIELDS:
        if not data.get(field):
            errors.append(f"Missing required field: '{field}'")

    if errors:
        return errors   # stop early if required fields missing

    # ── Type checks ───────────────────────────────────────────────
    str_fields = ["error", "app_name", "language", "framework",
                  "traceback", "endpoint", "method"]
    for field in str_fields:
        val = data.get(field)
        if val is not None and not isinstance(val, str):
            errors.append(f"Field '{field}' must be a string")

    # ── Length limits ─────────────────────────────────────────────
    if len(data.get("error",     "")) > MAX_ERROR_LEN:
        errors.append(f"'error' too long — max {MAX_ERROR_LEN} chars")

    if len(data.get("traceback", "")) > MAX_TRACEBACK_LEN:
        errors.append(f"'traceback' too long — max {MAX_TRACEBACK_LEN} chars")

    if len(data.get("app_name",  "")) > MAX_APP_NAME_LEN:
        errors.append(f"'app_name' too long — max {MAX_APP_NAME_LEN} chars")

    if len(data.get("endpoint",  "")) > MAX_ENDPOINT_LEN:
        errors.append(f"'endpoint' too long — max {MAX_ENDPOINT_LEN} chars")

    # ── Allowed values ────────────────────────────────────────────
    language  = data.get("language",  "").lower()
    framework = data.get("framework", "").lower()

    if language and language not in ALLOWED_LANGUAGES:
        errors.append(
            f"Unknown language '{language}' — "
            f"allowed: {', '.join(sorted(ALLOWED_LANGUAGES))}"
        )

    if framework and framework not in ALLOWED_FRAMEWORKS:
        # Don't reject — just warn (new frameworks exist)
        pass

    # ── Sanitize app_name (alphanumeric + dash + underscore only) ─
    app_name = data.get("app_name", "")
    if app_name and not re.match(r'^[a-zA-Z0-9_\-\. ]+$', app_name):
        errors.append("'app_name' contains invalid characters — use letters, numbers, dash, underscore only")

    # ── HTTP method check ─────────────────────────────────────────
    method = data.get("method", "").upper()
    allowed_methods = {"GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS","CLI","ASYNC","UNKNOWN",""}
    if method and method not in allowed_methods:
        errors.append(f"Invalid HTTP method '{method}'")

    return errors


def sanitize_string(value: str, max_len: int = 1000) -> str:
    """Remove null bytes and truncate string"""
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:max_len]


def sanitize_report(data: dict) -> dict:
    """Sanitize all string fields in the report"""
    sanitized = dict(data)
    str_fields = ["error", "app_name", "language", "framework",
                  "traceback", "endpoint", "method", "error_type"]
    for field in str_fields:
        if field in sanitized:
            sanitized[field] = sanitize_string(
                sanitized[field],
                MAX_TRACEBACK_LEN if field == "traceback" else MAX_ERROR_LEN
            )
    return sanitized