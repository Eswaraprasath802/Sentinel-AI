"""
agent_server/server.py
Sentinel Central Agent Server

FIXES APPLIED:
✅ API key authentication (X-Sentinel-Key header)
✅ Input validation layer (required fields + type checks)
✅ Request logging for observability
✅ Rate limiting per app_name
✅ Rollback endpoint
✅ Health check with component status
"""

import os
import time
import logging
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from flask import Flask, request, jsonify, g
from dotenv import load_dotenv
from elastic_mcp  import ElasticMCP
from ai_healer    import AIHealer
from fixes        import AutoFixer
from notifier     import SentinelNotifier
from monitor      import SentinelMonitor
from validator    import validate_report   # ← new validation layer

load_dotenv()
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("sentinel.server")

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────
API_KEY      = os.getenv("SENTINEL_API_KEY", "")
RATE_LIMIT   = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))

# ── Boot components ───────────────────────────────────────────────
mcp = ElasticMCP(
    elastic_url  = os.getenv("ELASTIC_URL",      ""),
    elastic_user = os.getenv("ELASTIC_USER",     "elastic"),
    elastic_pass = os.getenv("ELASTIC_PASSWORD", ""),
    app_name     = "sentinel-server"
)
notifier = SentinelNotifier(
    email_to     = os.getenv("ALERT_EMAIL",   ""),
    smtp_user    = os.getenv("SMTP_USER",     ""),
    smtp_pass    = os.getenv("SMTP_PASS",     ""),
    whatsapp_to  = os.getenv("WHATSAPP_TO",   ""),
    twilio_sid   = os.getenv("TWILIO_SID",    ""),
    twilio_token = os.getenv("TWILIO_TOKEN",  ""),
    app_name     = "sentinel-server"
)
healer  = AIHealer(api_key=os.getenv("GEMINI_API_KEY", ""), elastic_mcp=mcp)
fixer   = AutoFixer(elastic_mcp=mcp)
monitor = SentinelMonitor(healer=healer, fixer=fixer,
                          notifier=notifier, mcp=mcp)
monitor.start()

# ── Rate limit tracker ────────────────────────────────────────────
_rate_tracker = defaultdict(list)   # app_name → [timestamps]


# ── Auth middleware ───────────────────────────────────────────────
@app.before_request
def authenticate():
    """
    ✅ API key authentication
    Skip auth for /health (public endpoint)
    All other endpoints require X-Sentinel-Key header
    """
    if request.path == "/health":
        return None   # public

    if not API_KEY:
        return None   # auth disabled if no key set in .env

    key = request.headers.get("X-Sentinel-Key", "")
    if not key:
        logger.warning(f"[Auth] Missing key from {request.remote_addr}")
        return jsonify({"error": "Missing X-Sentinel-Key header"}), 401

    # Constant-time comparison to prevent timing attacks
    if not _safe_compare(key, API_KEY):
        logger.warning(f"[Auth] Invalid key from {request.remote_addr}")
        return jsonify({"error": "Invalid API key"}), 401


# ── Request logging (observability) ──────────────────────────────
@app.before_request
def log_request():
    g._start_time = time.time()

@app.after_request
def log_response(response):
    duration = int((time.time() - getattr(g, "_start_time", time.time())) * 1000)
    logger.info(
        f"{request.method} {request.path} → "
        f"{response.status_code} in {duration}ms"
    )
    return response


# ── Routes ────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Public health check — shows component status"""
    return jsonify({
        "status":    "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "elastic_mcp": mcp.is_connected(),
            "gemini":      healer.is_ready(),
            "queue_size":  monitor.queue_size()
        }
    })


@app.route("/report", methods=["POST"])
def report():
    """
    ✅ Validated + authenticated error report endpoint
    Called by ALL language SDKs
    """
    # ── Parse JSON ────────────────────────────────────────────────
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    # ── Validate input ────────────────────────────────────────────
    errors = validate_report(data)
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    # ── Rate limiting ─────────────────────────────────────────────
    app_name = data.get("app_name", "unknown")
    if _is_rate_limited(app_name):
        return jsonify({
            "error": f"Rate limit exceeded — max {RATE_LIMIT} reports/min per app"
        }), 429

    # ── Push to monitor queue ─────────────────────────────────────
    monitor.report(data)
    logger.info(f"[Report] Received from {app_name} ({data.get('language','?')}/{data.get('framework','?')})")

    return jsonify({
        "status":  "received",
        "message": "Sentinel is diagnosing your error"
    }), 202


@app.route("/rollback/<incident_id>", methods=["POST"])
def rollback(incident_id: str):
    """
    ✅ Rollback endpoint — undo a fix if it made things worse
    """
    data     = request.get_json(force=True, silent=True) or {}
    fix_type = data.get("fix_type", "")

    if not fix_type:
        return jsonify({"error": "Missing fix_type"}), 400

    result = fixer.rollback(fix_type)
    if result["success"]:
        logger.info(f"[Rollback] {fix_type} rolled back for incident {incident_id}")
        return jsonify({"status": "rolled_back", "action": result.get("action")}), 200
    else:
        return jsonify({"status": "rollback_failed", "reason": result.get("reason")}), 500


@app.route("/incidents", methods=["GET"])
def get_incidents():
    """Get recent incidents"""
    limit  = min(int(request.args.get("limit", 20)), 100)
    recent = list(monitor.incidents)[:limit]
    return jsonify(recent)


@app.route("/stats", methods=["GET"])
def get_stats():
    """Get stats from Elastic MCP"""
    return jsonify(mcp.get_stats())


@app.route("/incidents/<incident_id>/resolve", methods=["POST"])
def resolve_incident(incident_id: str):
    """Manually mark incident as resolved"""
    mcp.update_incident_status(incident_id, "manually_resolved")
    return jsonify({"status": "resolved"})


# ── Helpers ───────────────────────────────────────────────────────

def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison — prevents timing attacks"""
    return hashlib.sha256(a.encode()).digest() == \
           hashlib.sha256(b.encode()).digest()


def _is_rate_limited(app_name: str) -> bool:
    """Simple sliding window rate limiter"""
    now    = time.time()
    window = 60   # 1 minute window
    _rate_tracker[app_name] = [
        t for t in _rate_tracker[app_name] if now - t < window
    ]
    if len(_rate_tracker[app_name]) >= RATE_LIMIT:
        return True
    _rate_tracker[app_name].append(now)
    return False


# ── Start ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    auth = "enabled" if API_KEY else "disabled (set SENTINEL_API_KEY)"
    print(f"\n[Sentinel] 🚀 Agent Server starting on port {port}")
    print(f"[Sentinel] 🔐 Auth: {auth}")
    print(f"[Sentinel] 📊 Elastic MCP: {'✅ Connected' if mcp.is_connected() else '❌ Offline'}")
    print(f"[Sentinel] 🤖 Gemini: {'✅ Ready' if healer.is_ready() else '❌ No API key'}\n")
    app.run(host="0.0.0.0", port=port, debug=False)