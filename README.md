# 🛡️ Sentinel SDK v2 — AI Auto-Healing Plugin

> Add 2 lines to any web app. When something breaks, Sentinel detects, diagnoses, fixes, and alerts — automatically.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Node](https://img.shields.io/badge/Node.js-18+-green.svg)](https://nodejs.org)
[![PHP](https://img.shields.io/badge/PHP-8.0+-purple.svg)](https://php.net)

---

## ⚡ What It Does

When your software breaks, Sentinel:

1. 🚨 **Alerts immediately** → Terminal + Email + WhatsApp
2. 🧠 **Diagnoses with Gemini AI** via Elastic MCP context
3. 🔧 **Auto-fixes silently** in background
4. ✅ **Confirms the fix** → Terminal + Email + WhatsApp
5. 📊 **Logs everything** to Elasticsearch for future learning

---

## 🏗️ Architecture

```
Sentinel Agent Server (Python — runs on cloud)
        ↑  HTTP POST /report
        │
  ┌─────┼──────┬────────┐
  │     │      │        │
Flask  Node   Laravel  Spring Boot (coming soon)
Django Express  PHP     Ruby Rails  (coming soon)
```

---

## 🚀 Quick Start

### Python (Flask / FastAPI / Django)
```python
from sentinel_sdk import Sentinel
Sentinel(api_key="GEMINI_KEY", elastic_url="...", elastic_password="...").attach(app)
```

### Node.js (Express)
```javascript
const Sentinel = require("./sdks/node/node_sdk/sentinel");
new Sentinel({ appName: "MyApp" }).attach(app);
```

### PHP (Laravel)
```php
// app/Exceptions/Handler.php
Sentinel::report($exception);
```

---

## 📁 Structure

```
sentinel-plugin-v2/
├── agent_server/        ← Central AI Brain
│   ├── server.py        ← Flask API (receives all reports)
│   ├── monitor.py       ← Background processor
│   ├── elastic_mcp.py   ← Elastic MCP tools
│   ├── ai_healer.py     ← Gemini 2.5 Pro diagnosis
│   ├── fixes.py         ← Safe auto-fix engine
│   └── notifier.py      ← Terminal + Email + WhatsApp
│
├── sdks/
│   ├── python/          ← Flask / FastAPI / Django
│   ├── node/            ← Express / Next.js / Browser
│   └── php/             ← Laravel
│
└── examples/
    ├── flask_app/
    ├── fastapi_app/
    └── express_app/
```

---

## 🔑 Getting API Keys

| Service | Link | Cost |
|---|---|---|
| Gemini AI | https://aistudio.google.com/app/apikey | Free |
| Elasticsearch | https://cloud.elastic.co | 14-day free trial |
| Twilio WhatsApp | https://console.twilio.com | Free sandbox |
| Gmail SMTP | Gmail → Security → App Passwords | Free |

---

## 🛠️ Setup

```bash
# 1. Clone
git clone https://github.com/Eswaraprasath802/Sentinel-AI.git
cd Sentinel-AI

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp agent_server/.env.example agent_server/.env
# Fill in your API keys

# 4. Start Agent Server
cd agent_server
python server.py

# 5. Add to your app (2 lines!)
```

---

## 🏆 Built For

Google Cloud Rapid Agent Hackathon 2026
- Platform: Google Cloud Agent Builder
- AI: Gemini 2.5 Pro
- Partner Track: Elastic MCP

---

## 📄 License

MIT License — free for everyone to use, modify, and distribute.