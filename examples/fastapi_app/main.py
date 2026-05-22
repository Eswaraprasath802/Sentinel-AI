"""
FastAPI Example — Sentinel SDK
"""

from fastapi import FastAPI
from sentinel_sdk import Sentinel

app = FastAPI()

# ── 2 Lines ───────────────────────────────────────────────────────
Sentinel(api_key="YOUR_GEMINI_API_KEY", app_name="FastAPIDemo").attach(app)
# ─────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"status": "running"}

@app.get("/crash")
def crash():
    raise ConnectionError("DB connection refused")
