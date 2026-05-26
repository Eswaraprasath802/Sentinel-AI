"""
agent_server/notifier.py
Sentinel — Async Alert Engine

FIXES APPLIED:
✅ Async notifications (non-blocking — fire in background thread)
✅ Notification retry (3 attempts on failure)
✅ Observability — logs every alert sent/failed
✅ Alert deduplication (don't spam same alert twice)
"""

import smtplib
import logging
import threading
import time
import hashlib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import defaultdict

logger = logging.getLogger("sentinel.notifier")

MAX_RETRY        = 3
RETRY_DELAY      = 2   # seconds between retries
DEDUP_WINDOW     = 300 # 5 minutes — don't re-alert same error


class SentinelNotifier:
    def __init__(self, app_name: str = "MyApp",
                 email_to: str = "", email_from: str = "",
                 smtp_host: str = "smtp.gmail.com", smtp_port: int = 587,
                 smtp_user: str = "", smtp_pass: str = "",
                 whatsapp_to: str = "", twilio_sid: str = "",
                 twilio_token: str = "",
                 twilio_from: str = "whatsapp:+14155238886"):
        self.app_name    = app_name
        self.email_to    = email_to
        self.email_from  = email_from or smtp_user
        self.smtp_host   = smtp_host
        self.smtp_port   = smtp_port
        self.smtp_user   = smtp_user
        self.smtp_pass   = smtp_pass
        self.whatsapp_to = whatsapp_to
        self.twilio_sid  = twilio_sid
        self.twilio_token= twilio_token
        self.twilio_from = twilio_from
        self._dedup      = {}   # key → last_sent timestamp

    # ── Stage 1: Problem Detected ─────────────────────────────────
    def alert_detected(self, event: dict):
        """✅ Non-blocking — fires in background thread"""
        threading.Thread(
            target = self._do_alert_detected,
            args   = (event,),
            daemon = True
        ).start()

    def _do_alert_detected(self, event: dict):
        error    = event.get("error", "")
        language = event.get("language",  "unknown")
        framework= event.get("framework", "unknown")
        app      = event.get("app_name",  self.app_name)
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Deduplication ─────────────────────────────────────────
        if self._is_duplicate(f"detected:{error[:50]}"):
            logger.info(f"[Notifier] Skipped duplicate alert for: {error[:50]}")
            return

        # ── Terminal (always sync — just a print) ─────────────────
        print(f"\n\033[91m{'━'*62}\033[0m")
        print(f"\033[91m🚨  SENTINEL — PROBLEM DETECTED  [{ts}]\033[0m")
        print(f"\033[91m{'━'*62}\033[0m")
        print(f"  App       : {app}")
        print(f"  Language  : {language}/{framework}")
        print(f"  Error     : {error[:80]}")
        print(f"  ⏳ Gemini AI diagnosing via Elastic MCP...")
        print(f"\033[91m{'━'*62}\033[0m\n")

        # ── Email (async + retry) ─────────────────────────────────
        if self.email_to:
            self._send_with_retry(
                self._send_email,
                subject = f"🚨 Sentinel Alert — {app}",
                body    = (
                    f"<h2>🚨 Problem Detected</h2>"
                    f"<p><b>App:</b> {app}</p>"
                    f"<p><b>Language:</b> {language}/{framework}</p>"
                    f"<p><b>Time:</b> {ts}</p>"
                    f"<p><b>Error:</b> {error}</p>"
                    f"<p>⏳ AI diagnosing...</p>"
                )
            )

        # ── WhatsApp (async + retry) ──────────────────────────────
        if self.whatsapp_to:
            self._send_with_retry(
                self._send_whatsapp,
                message = (
                    f"🚨 *SENTINEL ALERT*\n"
                    f"App: {app}\n"
                    f"Language: {language}/{framework}\n"
                    f"Error: {error[:80]}\n"
                    f"⏳ AI diagnosing..."
                )
            )

    # ── Stage 2: Fix Applied ──────────────────────────────────────
    def alert_resolved(self, incident: dict):
        """✅ Non-blocking — fires in background thread"""
        threading.Thread(
            target = self._do_alert_resolved,
            args   = (incident,),
            daemon = True
        ).start()

    def _do_alert_resolved(self, incident: dict):
        diag     = incident.get("diagnosis",  {})
        fix      = incident.get("fix_result", {})
        app      = incident.get("app_name",   self.app_name)
        language = incident.get("language",   "unknown")
        action   = fix.get("action_taken") or fix.get("skipped_reason", "none")
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n\033[92m{'━'*62}\033[0m")
        print(f"\033[92m✅  SENTINEL — FIX APPLIED  [{ts}]\033[0m")
        print(f"\033[92m{'━'*62}\033[0m")
        print(f"  App         : {app} ({language})")
        print(f"  Root Cause  : {diag.get('root_cause','?')}")
        print(f"  Confidence  : {diag.get('confidence','?')}%")
        print(f"  Action      : {action}")
        print(f"  Rollback    : {'✅ Available' if fix.get('rollback_available') else '—'}")
        print(f"  Status      : \033[92m✅ AUTO-FIXED\033[0m")
        print(f"\033[92m{'━'*62}\033[0m\n")

        if self.email_to:
            self._send_with_retry(
                self._send_email,
                subject = f"✅ Fixed — {app}",
                body    = (
                    f"<h2>✅ Auto-Fixed</h2>"
                    f"<table>"
                    f"<tr><td><b>App</b></td><td>{app} ({language})</td></tr>"
                    f"<tr><td><b>Time</b></td><td>{ts}</td></tr>"
                    f"<tr><td><b>Root Cause</b></td><td>{diag.get('root_cause','?')}</td></tr>"
                    f"<tr><td><b>Action</b></td><td>{action}</td></tr>"
                    f"<tr><td><b>Confidence</b></td><td>{diag.get('confidence','?')}%</td></tr>"
                    f"</table>"
                )
            )

        if self.whatsapp_to:
            self._send_with_retry(
                self._send_whatsapp,
                message = (
                    f"✅ *SENTINEL — FIXED*\n"
                    f"App: {app}\n"
                    f"Root Cause: {diag.get('root_cause','?')}\n"
                    f"Action: {action}\n"
                    f"Confidence: {diag.get('confidence','?')}%"
                )
            )

    # ── Retry wrapper ─────────────────────────────────────────────
    def _send_with_retry(self, fn, **kwargs):
        """Retry sending notification up to MAX_RETRY times"""
        for attempt in range(1, MAX_RETRY + 1):
            try:
                fn(**kwargs)
                logger.info(f"[Notifier] {fn.__name__} sent OK (attempt {attempt})")
                return
            except Exception as e:
                logger.warning(f"[Notifier] {fn.__name__} failed attempt {attempt}: {e}")
                if attempt < MAX_RETRY:
                    time.sleep(RETRY_DELAY * attempt)
        logger.error(f"[Notifier] {fn.__name__} failed after {MAX_RETRY} attempts")

    # ── Deduplication ─────────────────────────────────────────────
    def _is_duplicate(self, key: str) -> bool:
        now  = time.time()
        last = self._dedup.get(key, 0)
        if now - last < DEDUP_WINDOW:
            return True
        self._dedup[key] = now
        return False

    # ── Email ─────────────────────────────────────────────────────
    def _send_email(self, subject: str, body: str):
        if not self.smtp_user or not self.smtp_pass:
            logger.warning("[Notifier] Email skipped — no SMTP credentials")
            return
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.email_from
        msg["To"]      = self.email_to
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
            s.starttls()
            s.login(self.smtp_user, self.smtp_pass)
            s.sendmail(self.email_from, self.email_to, msg.as_string())

    # ── WhatsApp ──────────────────────────────────────────────────
    def _send_whatsapp(self, message: str):
        if not self.twilio_sid or not self.twilio_token:
            logger.warning("[Notifier] WhatsApp skipped — no Twilio credentials")
            return
        from twilio.rest import Client
        Client(self.twilio_sid, self.twilio_token).messages.create(
            body  = message,
            from_ = self.twilio_from,
            to    = self.whatsapp_to
        )