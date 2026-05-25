"""
agent_server/server.py
Sentinel Central Agent Server
Receives error reports from ANY language SDK via HTTP POST
Runs Gemini AI + Elastic MCP + Auto-Fix + Alerts
"""

from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from elastic_mcp import ElasticMCP
from ai_healer   import AIHealer
from fixes       import AutoFixer
from notifier    import SentinelNotifier
from monitor     import SentinelMonitor

load_dotenv()

app = Flask(__name__)

# ── Boot all components ONCE ──────────────────────────────────────
mcp      = ElasticMCP(
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

# ─────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """SDK health check endpoint"""
    return jsonify({
        "status":  "running",
        "elastic": mcp.is_connected(),
        "gemini":  healer.is_ready()
    })


@app.route("/report", methods=["POST"])
def report():
    """
    Universal error report endpoint.
    Called by ALL language SDKs (Python, Node, PHP, Java, Ruby, Go...)

    Expected JSON body:
    {
        "app_name":   "MyApp",
        "framework":  "laravel",
        "language":   "php",
        "error":      "SQLSTATE[HY000]: General error",
        "error_type": "QueryException",
        "traceback":  "...",
        "endpoint":   "/api/users",
        "method":     "GET",
        "timestamp":  "2025-01-01T00:00:00Z"
    }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Required field check
    if not data.get("error"):
        return jsonify({"error": "Missing 'error' field"}), 400

    # Push to monitor queue
    monitor.report(data)

    return jsonify({
        "status":  "received",
        "message": "Sentinel is diagnosing your error"
    }), 202


@app.route("/incidents", methods=["GET"])
def get_incidents():
    """Get recent incidents — used by dashboard"""
    limit  = int(request.args.get("limit", 20))
    recent = list(monitor.incidents)[:limit]
    return jsonify(recent)


@app.route("/stats", methods=["GET"])
def get_stats():
    """Get incident stats from Elastic MCP"""
    return jsonify(mcp.get_stats())


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"\n[Sentinel Agent Server] Running on port {port}")
    print(f"[Sentinel Agent Server] Elastic MCP: {'✅ Connected' if mcp.is_connected() else '❌ Offline'}")
    app.run(host="0.0.0.0", port=port, debug=False)
