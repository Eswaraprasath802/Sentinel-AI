"""
agent_server/notifier.py
Sentinel — Terminal + Email + WhatsApp Alerts
"""

import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("sentinel.notifier")


class SentinelNotifier:
    def __init__(self, app_name: str = "MyApp",
                 email_to: str = "", email_from: str = "",
                 smtp_host: str = "smtp.gmail.com", smtp_port: int = 587,
                 smtp_user: str = "", smtp_pass: str = "",
                 whatsapp_to: str = "", twilio_sid: str = "",
                 twilio_token: str = "", twilio_from: str = "whatsapp:+14155238886"):
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

    def alert_detected(self, event: dict):
        error    = event.get("error", "")
        language = event.get("language", "unknown")
        framework= event.get("framework", "unknown")
        app      = event.get("app_name", self.app_name)
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Terminal
        print(f"\n\033[91m{'━'*62}\033[0m")
        print(f"\033[91m🚨  SENTINEL — PROBLEM DETECTED  [{ts}]\033[0m")
        print(f"\033[91m{'━'*62}\033[0m")
        print(f"  App       : {app}")
        print(f"  Language  : {language}/{framework}")
        print(f"  Error     : {error[:80]}")
        print(f"  ⏳ Gemini AI diagnosing via Elastic MCP...")
        print(f"\033[91m{'━'*62}\033[0m\n")

        if self.email_to:
            self._send_email(
                f"🚨 Sentinel Alert — {app}",
                f"<h2>Problem Detected</h2><p><b>App:</b> {app}</p>"
                f"<p><b>Language:</b> {language}/{framework}</p>"
                f"<p><b>Error:</b> {error}</p>"
                f"<p>⏳ AI diagnosing...</p>"
            )
        if self.whatsapp_to:
            self._send_whatsapp(
                f"🚨 *SENTINEL ALERT*\nApp: {app}\n"
                f"Language: {language}/{framework}\n"
                f"Error: {error[:80]}\n⏳ AI diagnosing..."
            )

    def alert_resolved(self, incident: dict):
        diag     = incident.get("diagnosis",  {})
        fix      = incident.get("fix_result", {})
        app      = incident.get("app_name",   self.app_name)
        language = incident.get("language",   "unknown")
        action   = fix.get("action_taken") or fix.get("skipped_reason", "none")

        print(f"\n\033[92m{'━'*62}\033[0m")
        print(f"\033[92m✅  SENTINEL — FIX APPLIED\033[0m")
        print(f"\033[92m{'━'*62}\033[0m")
        print(f"  App         : {app} ({language})")
        print(f"  Root Cause  : {diag.get('root_cause','?')}")
        print(f"  Confidence  : {diag.get('confidence','?')}%")
        print(f"  Action      : {action}")
        print(f"  Status      : \033[92m✅ AUTO-FIXED\033[0m")
        print(f"\033[92m{'━'*62}\033[0m\n")

        if self.email_to:
            self._send_email(
                f"✅ Fixed — {app}",
                f"<h2>✅ Auto-Fixed</h2>"
                f"<p><b>Root Cause:</b> {diag.get('root_cause','?')}</p>"
                f"<p><b>Action:</b> {action}</p>"
                f"<p><b>Confidence:</b> {diag.get('confidence','?')}%</p>"
            )
        if self.whatsapp_to:
            self._send_whatsapp(
                f"✅ *SENTINEL — FIXED*\nApp: {app}\n"
                f"Root Cause: {diag.get('root_cause','?')}\n"
                f"Action: {action}\n"
                f"Confidence: {diag.get('confidence','?')}%"
            )

    def _send_email(self, subject: str, body: str):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self.email_from
            msg["To"]      = self.email_to
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                s.starttls()
                s.login(self.smtp_user, self.smtp_pass)
                s.sendmail(self.email_from, self.email_to, msg.as_string())
        except Exception as e:
            logger.warning(f"[Sentinel] Email failed: {e}")

    def _send_whatsapp(self, message: str):
        try:
            from twilio.rest import Client
            Client(self.twilio_sid, self.twilio_token).messages.create(
                body=message, from_=self.twilio_from, to=self.whatsapp_to
            )
        except Exception as e:
            logger.warning(f"[Sentinel] WhatsApp failed: {e}")
