"""
Sentinel Notifier
─────────────────
Sends alerts to ALL channels simultaneously:
  1. Terminal  — colored, formatted output in server logs
  2. Email     — via SMTP (Gmail / any provider)
  3. WhatsApp  — via Twilio WhatsApp API (free sandbox available)

Called TWICE per incident:
  • Immediately when error is detected  → "🚨 DETECTED"
  • After fix is attempted              → "✅ FIXED" or "⚠️ NEEDS ATTENTION"
"""

import os
import smtplib
import threading
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── ANSI colors for terminal ──────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"
    BG_RED = "\033[41m"

SEV_COLOR = {
    "critical": C.RED,
    "high":     C.YELLOW,
    "medium":   C.CYAN,
    "low":      C.GREEN,
}


class SentinelNotifier:
    """
    Usage inside Sentinel config:

        Sentinel(
            api_key      = "GEMINI_KEY",
            email_to     = "you@example.com",
            email_from   = "alerts@example.com",
            smtp_host    = "smtp.gmail.com",
            smtp_port    = 587,
            smtp_user    = "alerts@example.com",
            smtp_pass    = "app_password",
            whatsapp_to  = "whatsapp:+919876543210",
            twilio_sid   = "ACxxxx",
            twilio_token = "xxxx",
            twilio_from  = "whatsapp:+14155238886",
        ).attach(app)
    """

    def __init__(
        self,
        # Email
        email_to:     str = None,
        email_from:   str = None,
        smtp_host:    str = "smtp.gmail.com",
        smtp_port:    int = 587,
        smtp_user:    str = None,
        smtp_pass:    str = None,
        # WhatsApp (Twilio)
        whatsapp_to:  str = None,
        twilio_sid:   str = None,
        twilio_token: str = None,
        twilio_from:  str = "whatsapp:+14155238886",
        # App info
        app_name:     str = "MyApp",
    ):
        # Email config (fallback to env vars)
        self.email_to    = email_to    or os.getenv("SENTINEL_EMAIL_TO")
        self.email_from  = email_from  or os.getenv("SENTINEL_EMAIL_FROM")
        self.smtp_host   = smtp_host
        self.smtp_port   = smtp_port
        self.smtp_user   = smtp_user   or os.getenv("SENTINEL_SMTP_USER")
        self.smtp_pass   = smtp_pass   or os.getenv("SENTINEL_SMTP_PASS")

        # WhatsApp config (fallback to env vars)
        self.whatsapp_to  = whatsapp_to  or os.getenv("SENTINEL_WHATSAPP_TO")
        self.twilio_sid   = twilio_sid   or os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_token = twilio_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from  = twilio_from  or os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

        self.app_name = app_name

    # ── Public API ─────────────────────────────────────────────────────────────

    def alert_detected(self, event: dict):
        """Fire immediately when an error is detected — before fix attempt."""
        msg = self._build_detected_message(event)
        self._dispatch_all(msg, event, phase="detected")

    def alert_resolved(self, incident: dict):
        """Fire after fix has been attempted — with result."""
        msg = self._build_resolved_message(incident)
        self._dispatch_all(msg, incident, phase="resolved")

    # ── Message builders ──────────────────────────────────────────────────────

    def _build_detected_message(self, event: dict) -> dict:
        sev   = event.get("severity", "unknown").upper()
        error = event.get("error", event.get("message", "Unknown error"))
        path  = event.get("context", {}).get("path", "")
        fw    = event.get("framework", "")
        ts    = event.get("timestamp", datetime.utcnow().isoformat())[:19].replace("T", " ")

        return {
            "phase":    "DETECTED",
            "emoji":    "🚨",
            "severity": sev,
            "error":    error,
            "path":     path,
            "framework": fw,
            "timestamp": ts,
            "subject":  f"[Sentinel 🚨] {sev} error in {self.app_name}",
        }

    def _build_resolved_message(self, incident: dict) -> dict:
        diag       = incident.get("diagnosis", {})
        fix_result = incident.get("fix_result", {})
        root_cause = diag.get("root_cause", "Unknown")
        sev        = diag.get("severity", "unknown").upper()
        confidence = diag.get("confidence", 0)
        fix_type   = fix_result.get("fix_type", "manual")
        success    = fix_result.get("success", False)
        action     = fix_result.get("action_taken") or fix_result.get("skipped_reason", "—")
        steps      = diag.get("fix_steps") or [diag.get("explanation", "")]
        ts         = incident.get("timestamp", datetime.utcnow().isoformat())[:19].replace("T", " ")

        return {
            "phase":      "RESOLVED" if success else "NEEDS_ATTENTION",
            "emoji":      "✅" if success else "⚠️",
            "severity":   sev,
            "root_cause": root_cause,
            "confidence": confidence,
            "fix_type":   fix_type,
            "success":    success,
            "action":     action,
            "steps":      steps,
            "timestamp":  ts,
            "subject":    f"[Sentinel {'✅' if success else '⚠️'}] {'Fixed' if success else 'Needs attention'}: {root_cause[:60]}",
        }

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def _dispatch_all(self, msg: dict, raw: dict, phase: str):
        """Send to all channels in parallel background threads."""
        for fn in [self._terminal, self._send_email, self._send_whatsapp]:
            t = threading.Thread(target=self._safe_call, args=(fn, msg, raw), daemon=True)
            t.start()

    def _safe_call(self, fn, msg, raw):
        try:
            fn(msg, raw)
        except Exception as e:
            print(f"{C.DIM}[Sentinel] Notifier error in {fn.__name__}: {e}{C.RESET}")

    # ── 1. Terminal ───────────────────────────────────────────────────────────

    def _terminal(self, msg: dict, raw: dict):
        sev_c = SEV_COLOR.get(msg["severity"].lower(), C.WHITE)

        if msg["phase"] == "DETECTED":
            print(f"\n{C.BOLD}{C.RED}{'━'*60}{C.RESET}")
            print(f"{C.BOLD}{msg['emoji']}  SENTINEL — PROBLEM DETECTED  [{msg['timestamp']}]{C.RESET}")
            print(f"{C.BOLD}{'━'*60}{C.RESET}")
            print(f"  {C.BOLD}App      :{C.RESET} {self.app_name}")
            print(f"  {C.BOLD}Severity :{C.RESET} {sev_c}{msg['severity']}{C.RESET}")
            print(f"  {C.BOLD}Error    :{C.RESET} {msg['error'][:120]}")
            if msg.get("path"):
                print(f"  {C.BOLD}Path     :{C.RESET} {msg['path']}")
            if msg.get("framework"):
                print(f"  {C.BOLD}Framework:{C.RESET} {msg['framework']}")
            print(f"{C.DIM}  ⏳ Diagnosing with Gemini AI...{C.RESET}")
            print(f"{C.BOLD}{'━'*60}{C.RESET}\n")

        else:  # RESOLVED or NEEDS_ATTENTION
            ok = msg["success"]
            color = C.GREEN if ok else C.YELLOW
            print(f"\n{C.BOLD}{color}{'━'*60}{C.RESET}")
            print(f"{C.BOLD}{msg['emoji']}  SENTINEL — {'FIX APPLIED' if ok else 'NEEDS ATTENTION'}  [{msg['timestamp']}]{C.RESET}")
            print(f"{C.BOLD}{color}{'━'*60}{C.RESET}")
            print(f"  {C.BOLD}Root Cause :{C.RESET} {msg['root_cause']}")
            print(f"  {C.BOLD}Confidence :{C.RESET} {C.CYAN}{msg['confidence']}%{C.RESET}")
            print(f"  {C.BOLD}Severity   :{C.RESET} {sev_c}{msg['severity']}{C.RESET}")
            print(f"  {C.BOLD}Fix Type   :{C.RESET} {msg['fix_type']}")
            print(f"  {C.BOLD}Action     :{C.RESET} {msg['action'][:120]}")
            if msg.get("steps"):
                print(f"  {C.BOLD}Steps      :{C.RESET}")
                for i, s in enumerate(msg["steps"][:3], 1):
                    print(f"    {C.DIM}{i}.{C.RESET} {s}")
            status = f"{C.GREEN}✅ AUTO-FIXED{C.RESET}" if ok else f"{C.YELLOW}⚠️  MANUAL ACTION NEEDED{C.RESET}"
            print(f"\n  Status: {status}")
            print(f"{C.BOLD}{color}{'━'*60}{C.RESET}\n")

    # ── 2. Email ──────────────────────────────────────────────────────────────

    def _send_email(self, msg: dict, raw: dict):
        if not all([self.email_to, self.email_from, self.smtp_user, self.smtp_pass]):
            return  # Email not configured — skip silently

        html = self._build_email_html(msg)
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg["subject"]
        mime["From"]    = f"Sentinel AI <{self.email_from}>"
        mime["To"]      = self.email_to
        mime.attach(MIMEText(self._build_email_plain(msg), "plain"))
        mime.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
            s.ehlo()
            s.starttls()
            s.login(self.smtp_user, self.smtp_pass)
            s.sendmail(self.email_from, self.email_to, mime.as_string())

    def _build_email_plain(self, msg: dict) -> str:
        if msg["phase"] == "DETECTED":
            return (
                f"SENTINEL ALERT — {msg['severity']} ERROR DETECTED\n\n"
                f"App      : {self.app_name}\n"
                f"Error    : {msg.get('error','')}\n"
                f"Time     : {msg['timestamp']}\n\n"
                f"Gemini AI is diagnosing the issue now...\n"
            )
        ok = msg["success"]
        return (
            f"SENTINEL — {'FIX APPLIED' if ok else 'NEEDS ATTENTION'}\n\n"
            f"Root Cause : {msg['root_cause']}\n"
            f"Confidence : {msg['confidence']}%\n"
            f"Action     : {msg['action']}\n"
            f"Status     : {'✅ Auto-fixed' if ok else '⚠️  Manual action needed'}\n"
        )

    def _build_email_html(self, msg: dict) -> str:
        sev   = msg.get("severity", "UNKNOWN")
        sev_color = {"CRITICAL":"#ff3d57","HIGH":"#ffb300","MEDIUM":"#00e5ff","LOW":"#00e676"}.get(sev, "#aaa")

        if msg["phase"] == "DETECTED":
            body_html = f"""
            <h2 style="color:#ff3d57">🚨 Problem Detected in {self.app_name}</h2>
            <table style="border-collapse:collapse;width:100%;font-family:monospace">
              <tr><td style="padding:8px;color:#888;width:130px">Severity</td>
                  <td style="padding:8px;color:{sev_color};font-weight:bold">{sev}</td></tr>
              <tr style="background:#111"><td style="padding:8px;color:#888">Error</td>
                  <td style="padding:8px">{msg.get('error','')[:200]}</td></tr>
              <tr><td style="padding:8px;color:#888">Time</td>
                  <td style="padding:8px">{msg['timestamp']}</td></tr>
              <tr style="background:#111"><td style="padding:8px;color:#888">Framework</td>
                  <td style="padding:8px">{msg.get('framework','—')}</td></tr>
            </table>
            <p style="color:#888;margin-top:20px">⏳ Gemini AI is diagnosing and attempting auto-fix...</p>
            """
        else:
            ok = msg["success"]
            status_color = "#00e676" if ok else "#ffb300"
            status_text  = "✅ Auto-Fixed" if ok else "⚠️ Needs Manual Attention"
            steps_html = "".join(
                f"<li style='margin:6px 0'>{s}</li>"
                for s in (msg.get("steps") or [])[:3]
            )
            body_html = f"""
            <h2 style="color:{status_color}">{msg['emoji']} {status_text}</h2>
            <table style="border-collapse:collapse;width:100%;font-family:monospace">
              <tr><td style="padding:8px;color:#888;width:130px">Root Cause</td>
                  <td style="padding:8px;font-weight:bold">{msg['root_cause']}</td></tr>
              <tr style="background:#111"><td style="padding:8px;color:#888">Confidence</td>
                  <td style="padding:8px;color:#00e5ff">{msg['confidence']}%</td></tr>
              <tr><td style="padding:8px;color:#888">Severity</td>
                  <td style="padding:8px;color:{sev_color}">{sev}</td></tr>
              <tr style="background:#111"><td style="padding:8px;color:#888">Fix Applied</td>
                  <td style="padding:8px">{msg['action'][:200]}</td></tr>
              <tr><td style="padding:8px;color:#888">Steps</td>
                  <td style="padding:8px"><ol style="margin:0;padding-left:18px">{steps_html}</ol></td></tr>
            </table>
            <p style="margin-top:16px;padding:12px;background:#111;border-left:4px solid {status_color};
               font-family:monospace">Status: <strong style="color:{status_color}">{status_text}</strong></p>
            """

        return f"""<!DOCTYPE html>
        <html><body style="background:#0a0c0f;color:#c8d0dc;font-family:sans-serif;padding:24px;max-width:600px">
          <div style="border:1px solid #1e2530;border-radius:8px;padding:24px;background:#111318">
            <div style="font-size:11px;color:#4a5568;letter-spacing:.1em;margin-bottom:16px">
              SENTINEL AI · {self.app_name}
            </div>
            {body_html}
            <div style="margin-top:24px;font-size:11px;color:#4a5568;border-top:1px solid #1e2530;padding-top:12px">
              Powered by Sentinel SDK + Google Gemini
            </div>
          </div>
        </body></html>"""

    # ── 3. WhatsApp (Twilio) ──────────────────────────────────────────────────

    def _send_whatsapp(self, msg: dict, raw: dict):
        if not all([self.whatsapp_to, self.twilio_sid, self.twilio_token]):
            return  # WhatsApp not configured — skip silently

        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)

            if msg["phase"] == "DETECTED":
                text = (
                    f"🚨 *SENTINEL ALERT* — {self.app_name}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"*Severity* : {msg['severity']}\n"
                    f"*Error*    : {msg.get('error','')[:100]}\n"
                    f"*Time*     : {msg['timestamp']}\n\n"
                    f"⏳ _Gemini AI diagnosing..._"
                )
            else:
                ok = msg["success"]
                text = (
                    f"{'✅' if ok else '⚠️'} *SENTINEL* — {'Fixed' if ok else 'Needs Attention'}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"*Cause*      : {msg['root_cause'][:80]}\n"
                    f"*Confidence* : {msg['confidence']}%\n"
                    f"*Action*     : {msg['action'][:80]}\n"
                    f"*Status*     : {'✅ Auto-fixed' if ok else '⚠️ Manual fix needed'}"
                )

            client.messages.create(
                from_=self.twilio_from,
                to=self.whatsapp_to,
                body=text,
            )
        except ImportError:
            print("[Sentinel] twilio not installed — pip install twilio")
        except Exception as e:
            print(f"[Sentinel] WhatsApp send failed: {e}")
