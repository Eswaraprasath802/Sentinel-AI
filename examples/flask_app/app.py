"""
Flask Example — Full Sentinel integration (Terminal + Email + WhatsApp).
"""
from flask import Flask, jsonify
from sentinel_sdk import Sentinel

app = Flask(__name__)

# ── Add Sentinel — just this block, nothing else changes ─────────────────────
Sentinel(
    api_key      = "YOUR_GEMINI_API_KEY",     # https://aistudio.google.com/app/apikey
    app_name     = "MyFlaskApp",

    # ── Email alerts (Gmail example) ──────────────────────────────────────────
    email_to     = "you@example.com",
    email_from   = "alerts@gmail.com",
    smtp_host    = "smtp.gmail.com",
    smtp_port    = 587,
    smtp_user    = "alerts@gmail.com",
    smtp_pass    = "your_gmail_app_password",  # gmail.com → Security → App Passwords

    # ── WhatsApp alerts (Twilio sandbox — free) ───────────────────────────────
    whatsapp_to  = "whatsapp:+919876543210",   # your WhatsApp number
    twilio_sid   = "ACxxxxxxxxxxxxxxxx",        # twilio.com → Console
    twilio_token = "your_twilio_auth_token",
    twilio_from  = "whatsapp:+14155238886",    # Twilio sandbox number
).attach(app)
# ─────────────────────────────────────────────────────────────────────────────


# ── Your existing routes — completely unchanged ───────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "ok"})

@app.route("/simulate/db-error")
def sim_db():
    raise ConnectionError("ECONNREFUSED: DB connection refused on port 5432")

@app.route("/simulate/missing-pkg")
def sim_pkg():
    import non_existent_package  # noqa

@app.route("/simulate/slow")
def sim_slow():
    import time; time.sleep(6)
    return jsonify({"msg": "slow"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
