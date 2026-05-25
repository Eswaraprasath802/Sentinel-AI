"""
Flask Example — Sentinel SDK
Just 2 lines to add AI auto-healing!
"""

from flask import Flask, jsonify
from sentinel_sdk import Sentinel

app = Flask(__name__)

# ── 2 Lines ───────────────────────────────────────────────────────
Sentinel(
    api_key      = "YOUR_GEMINI_API_KEY",
    app_name     = "FlaskDemo",
    elastic_url  = "https://your-deployment.es.io",
    elastic_password = "your_elastic_password",
    email_to     = "you@example.com",
    smtp_user    = "alerts@gmail.com",
    smtp_pass    = "gmail_app_password",
    whatsapp_to  = "whatsapp:+919876543210",
    twilio_sid   = "ACxxxxxxxx",
    twilio_token = "xxxxxxxx",
).attach(app)
# ─────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({"status": "running"})

@app.route("/crash")
def crash():
    raise ConnectionError("ECONNREFUSED: DB connection refused on port 5432")

if __name__ == "__main__":
    app.run(debug=False, port=5000)
