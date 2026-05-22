"""
notifier.py
Sentinel SDK — Alerting Engine
Sends alerts via Terminal + Email + WhatsApp
"""

import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class Notifier:
    def __init__(self, app_name: str, email_to: str = "",
                 smtp_user: str = "", smtp_pass: str = "",
                 whatsapp_to: str = "", twilio_sid: str = "",
                 twilio_token: str = ""):
        self.app_name     = app_name
        self.email_to     = email_to
        self.smtp_user    = smtp_user
        self.smtp_pass    = smtp_pass
        self.whatsapp_to  = whatsapp_to
        self.twilio_sid   = twilio_sid
        self.twilio_token = twilio_token

    # ─── Stage 1: Problem Detected ───────────────────────────────
    def alert_detected(self, error: str, severity: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._terminal_detected(error, severity, ts)
        if self.email_to:
            self._email_detected(error, severity, ts)
        if self.whatsapp_to:
            self._whatsapp_detected(error, severity, ts)

    # ─── Stage 2: Fix Applied ─────────────────────────────────────
    def alert_fixed(self, error: str, root_cause: str,
                    suggested_fix: str, confidence: int,
                    action_taken: str, severity: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._terminal_fixed(error, root_cause, suggested_fix,
                              confidence, action_taken, ts)
        if self.email_to:
            self._email_fixed(error, root_cause, suggested_fix,
                               confidence, action_taken, severity, ts)
        if self.whatsapp_to:
            self._whatsapp_fixed(root_cause, suggested_fix,
                                  confidence, action_taken)

    # ─── Terminal Alerts ──────────────────────────────────────────
    def _terminal_detected(self, error, severity, ts):
        sev_color = {"critical": "\033[91m", "high": "\033[93m",
                     "medium": "\033[94m", "low": "\033[92m"}
        c = sev_color.get(severity, "\033[91m")
        r = "\033[0m"
        print(f"\n{c}{'━'*62}{r}")
        print(f"{c}🚨  SENTINEL — PROBLEM DETECTED  [{ts}]{r}")
        print(f"{c}{'━'*62}{r}")
        print(f"  App      : {self.app_name}")
        print(f"  Severity : {c}{severity.upper()}{r}")
        print(f"  Error    : {error[:80]}")
        print(f"  ⏳ Gemini AI diagnosing via Elastic MCP...")
        print(f"{c}{'━'*62}{r}\n")

    def _terminal_fixed(self, error, root_cause, suggested_fix,
                         confidence, action_taken, ts):
        g = "\033[92m"
        r = "\033[0m"
        print(f"\n{g}{'━'*62}{r}")
        print(f"{g}✅  SENTINEL — FIX APPLIED{r}")
        print(f"{g}{'━'*62}{r}")
        print(f"  Root Cause  : {root_cause}")
        print(f"  Confidence  : {confidence}%")
        print(f"  Action      : {action_taken}")
        print(f"  Status      : {g}✅ AUTO-FIXED{r}")
        print(f"{g}{'━'*62}{r}\n")

    # ─── Email Alerts ─────────────────────────────────────────────
    def _email_detected(self, error, severity, ts):
        subject = f"🚨 [{severity.upper()}] Sentinel Alert — {self.app_name}"
        body    = f"<h2>🚨 Problem Detected</h2><p><b>App:</b> {self.app_name}</p><p><b>Time:</b> {ts}</p><p><b>Severity:</b> {severity.upper()}</p><p><b>Error:</b> {error}</p><p>⏳ Gemini AI is diagnosing...</p>"
        self._send_email(subject, body)

    def _email_fixed(self, error, root_cause, suggested_fix,
                      confidence, action_taken, severity, ts):
        subject = f"✅ [FIXED] Sentinel — {self.app_name}"
        body    = f"""
        <h2>✅ Incident Auto-Fixed</h2>
        <table>
          <tr><td><b>App</b></td><td>{self.app_name}</td></tr>
          <tr><td><b>Time</b></td><td>{ts}</td></tr>
          <tr><td><b>Severity</b></td><td>{severity.upper()}</td></tr>
          <tr><td><b>Error</b></td><td>{error[:100]}</td></tr>
          <tr><td><b>Root Cause</b></td><td>{root_cause}</td></tr>
          <tr><td><b>Fix Applied</b></td><td>{action_taken}</td></tr>
          <tr><td><b>AI Confidence</b></td><td>{confidence}%</td></tr>
        </table>
        <p style="color:green"><b>Status: AUTO-FIXED by Sentinel ✅</b></p>
        """
        self._send_email(subject, body)

    def _send_email(self, subject: str, body: str):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self.smtp_user
            msg["To"]      = self.email_to
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(self.smtp_user, self.smtp_pass)
                s.sendmail(self.smtp_user, self.email_to, msg.as_string())
        except Exception as e:
            print(f"[Sentinel] Email failed: {e}")

    # ─── WhatsApp Alerts ─────────────────────────────────────────
    def _whatsapp_detected(self, error, severity, ts):
        msg = (f"🚨 *SENTINEL ALERT*\n"
               f"App: {self.app_name}\n"
               f"Severity: {severity.upper()}\n"
               f"Error: {error[:80]}\n"
               f"⏳ AI diagnosing via Elastic MCP...")
        self._send_whatsapp(msg)

    def _whatsapp_fixed(self, root_cause, suggested_fix,
                         confidence, action_taken):
        msg = (f"✅ *SENTINEL — AUTO-FIXED*\n"
               f"App: {self.app_name}\n"
               f"Root Cause: {root_cause}\n"
               f"Action: {action_taken}\n"
               f"Confidence: {confidence}%\n"
               f"Status: ✅ FIXED")
        self._send_whatsapp(msg)

    def _send_whatsapp(self, message: str):
        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)
            client.messages.create(
                body=message,
                from_="whatsapp:+14155238886",
                to=self.whatsapp_to
            )
        except Exception as e:
            print(f"[Sentinel] WhatsApp failed: {e}")
