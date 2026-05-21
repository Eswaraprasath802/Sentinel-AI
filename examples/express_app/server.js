const express  = require("express");
const sentinel = require("../../node_sdk/sentinel");

const app = express();

// ── Add Sentinel — just this block ───────────────────────────────────────────
sentinel.attach(app, {
  apiKey:       "YOUR_GEMINI_API_KEY",
  appName:      "MyExpressApp",
  // Email
  emailTo:      "you@example.com",
  emailFrom:    "alerts@gmail.com",
  smtpUser:     "alerts@gmail.com",
  smtpPass:     "your_app_password",
  // WhatsApp
  whatsappTo:   "whatsapp:+919876543210",
  twilioSid:    "ACxxxxxxxxxxxxxxxx",
  twilioToken:  "your_twilio_auth_token",
});
// ─────────────────────────────────────────────────────────────────────────────

app.get("/", (req, res) => res.json({ status: "ok" }));

app.get("/simulate/error", (req, res) => {
  throw new Error("ECONNREFUSED: DB connection refused");
});

app.listen(3000, () => console.log("Server on http://localhost:3000"));
