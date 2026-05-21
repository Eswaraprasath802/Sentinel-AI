# 🛡️ Sentinel SDK v2 — AI Auto-Healing Plugin

Add **2 lines** to any web app. When something breaks, Sentinel:

1. 🚨 **Immediately alerts** → Terminal + Email + WhatsApp
2. 🧠 **Diagnoses** with Google Gemini AI
3. 🔧 **Auto-fixes** silently in background
4. ✅ **Confirms** the fix → Terminal + Email + WhatsApp

---

## ⚡ Quick Start

### Flask
```python
from sentinel_sdk import Sentinel

Sentinel(
    api_key     = "GEMINI_KEY",
    app_name    = "MyApp",
    email_to    = "you@example.com",
    smtp_user   = "alerts@gmail.com",
    smtp_pass   = "gmail_app_password",
    whatsapp_to = "whatsapp:+919876543210",
    twilio_sid  = "ACxxxxxxxx",
    twilio_token= "xxxxxxxx",
).attach(app)
```

### FastAPI
```python
from sentinel_sdk import Sentinel
Sentinel(api_key="GEMINI_KEY", ...).attach(app)
```

### Django  (in wsgi.py)
```python
from sentinel_sdk import Sentinel
Sentinel(api_key="GEMINI_KEY", ...).attach(application)
```

### Express / Node.js
```javascript
const sentinel = require('./sentinel_sdk/sentinel');
sentinel.attach(app, {
  apiKey: "GEMINI_KEY",
  emailTo: "you@example.com", smtpUser: "...", smtpPass: "...",
  whatsappTo: "whatsapp:+91...", twilioSid: "...", twilioToken: "..."
});
```

### Vanilla JS (browser)
```html
<script src="sentinel.browser.js" data-key="GEMINI_KEY"></script>
```

---

## 📲 What You Get When Something Breaks

**Terminal (instant):**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨  SENTINEL — PROBLEM DETECTED  [2025-05-18 03:12:01]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  App       : MyApp
  Severity  : CRITICAL
  Error     : ECONNREFUSED: DB connection refused on port 5432
  ⏳ Gemini AI diagnosing...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅  SENTINEL — FIX APPLIED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Root Cause : DB connection pool exhausted
  Confidence : 94%
  Action     : Reloaded .env + cleared connection cache
  Status: ✅ AUTO-FIXED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**WhatsApp:** Same info as a formatted WhatsApp message (2 messages per incident)
**Email:** Rich HTML email with full incident details (2 emails per incident)

---

## 📦 Install
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

## 🔑 Getting Free API Keys
| Service | Link | Cost |
|---------|------|------|
| Gemini AI | https://aistudio.google.com/app/apikey | Free |
| Twilio WhatsApp | https://console.twilio.com | Free sandbox |
| Gmail SMTP | gmail.com → Security → App Passwords | Free |
| Elasticsearch | https://cloud.elastic.co | 14-day free trial |

---

## 📁 Structure
```
sentinel_sdk/
  core.py       ← Main Sentinel class (auto-detects Flask/FastAPI/Django)
  monitor.py    ← Background queue + 2-stage alerting
  ai_healer.py  ← Gemini diagnosis + rule-based fallback
  fixes.py      ← Safe auto-fixes
  notifier.py   ← Terminal + Email + WhatsApp alerts
node_sdk/
  sentinel.js         ← Node.js/Express SDK
  sentinel.browser.js ← Vanilla JS browser snippet
examples/             ← Flask, FastAPI, Express examples
```
