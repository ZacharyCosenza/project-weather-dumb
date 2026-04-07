#!/usr/bin/env python3
"""
Weather app monitor — three modes:

  python -m weather.monitor startup   # send startup email with ngrok URL
  python -m weather.monitor check     # alert if predictions stale or web container down
  python -m weather.monitor test      # send a test email to verify SMTP config

Config:
  alert.email_from / alert.email_to   set in conf/base/parameters.yml
  ALERT_SMTP_PASSWORD                 set in .env (Gmail App Password)
"""

import json
import os
import smtplib
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from kedro.config import OmegaConfigLoader
from kedro.framework.project import settings

# ── Config ────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parents[3]  # project root

def _load_params() -> dict:
    conf_path = _ROOT / settings.CONF_SOURCE
    loader = OmegaConfigLoader(conf_source=str(conf_path))
    return loader["parameters"]


def _smtp_password() -> str:
    # Check .env first, then environment
    env_path = _ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ALERT_SMTP_PASSWORD="):
                return line.partition("=")[2].strip()
    return os.environ.get("ALERT_SMTP_PASSWORD", "")


PREDICTIONS_PATH = _ROOT / "data/03_primary/predictions.json"


# ── Email ─────────────────────────────────────────────────────────────────────

def _send(subject: str, body: str, email_from: str, email_to: list[str], password: str) -> None:
    if not email_from or not email_to or not password:
        print(f"[monitor] SMTP not configured — would have sent: {subject}", file=sys.stderr)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(email_to)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(email_from, password)
        s.sendmail(email_from, email_to, msg.as_string())
    print(f"[monitor] Email sent: {subject}")


# ── Checks ────────────────────────────────────────────────────────────────────

def _ngrok_url(retries: int = 15, interval: float = 1.0) -> str:
    for _ in range(retries):
        try:
            with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=2) as r:
                data = json.load(r)
            tunnels = data.get("tunnels", [])
            if tunnels:
                return tunnels[0]["public_url"]
        except Exception:
            pass
        time.sleep(interval)
    return ""


def _predictions_age_secs() -> float | None:
    if not PREDICTIONS_PATH.exists():
        return None
    return time.time() - PREDICTIONS_PATH.stat().st_mtime


def _container_running(name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


# ── Modes ─────────────────────────────────────────────────────────────────────

def startup() -> None:
    params        = _load_params()
    alert         = params.get("alert", {})
    web_container = alert.get("web_container", "weather-web")
    send          = lambda s, b: _send(s, b, alert["email_from"], alert["email_to"], _smtp_password())

    url = _ngrok_url(retries=60, interval=3.0)  # poll up to 3 min for Docker/ngrok to settle
    if not url:
        print("[monitor] ngrok URL not available after polling — skipping startup email. Check logs/ngrok.log", file=sys.stderr)
        return

    age      = _predictions_age_secs()
    age_line = f"Predictions last updated: {age:.0f}s ago" if age is not None else "Predictions file not yet written."

    send(
        "🌆 NYC Nowcast is live",
        f"The weather app started at {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\n"
        f"Public URL: {url}\n\n"
        f"Web container running: {_container_running(web_container)}\n"
        f"{age_line}",
    )


def check() -> None:
    params                = _load_params()
    alert                 = params.get("alert", {})
    web_container         = alert.get("web_container", "weather-web")
    stale_threshold_secs  = alert.get("stale_threshold_hours", 3) * 3600
    send                  = lambda s, b: _send(s, b, alert["email_from"], alert["email_to"], _smtp_password())

    issues = []

    age = _predictions_age_secs()
    if age is None:
        issues.append("predictions.json is missing entirely.")
    elif age > stale_threshold_secs:
        mtime = datetime.fromtimestamp(PREDICTIONS_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        issues.append(f"predictions.json has not been updated in {age/3600:.1f}h (last modified: {mtime}).")

    if not _container_running(web_container):
        issues.append(f"Docker container '{web_container}' is not running.")

    if issues:
        body = "The following issues were detected:\n\n"
        body += "\n".join(f"• {i}" for i in issues)
        body += "\n\nCheck with: docker compose ps && docker compose logs"
        send("⚠️ NYC Nowcast alert", body)
    else:
        print(f"[monitor] All checks passed (predictions age: {age:.0f}s, web container up)")


def test_email() -> None:
    params = _load_params()
    alert  = params.get("alert", {})
    _send(
        "✅ NYC Nowcast monitor — test email",
        f"SMTP is configured correctly. Sent at {datetime.now().strftime('%Y-%m-%d %H:%M')}.",
        alert["email_from"], alert["email_to"], _smtp_password(),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "startup":
        startup()
    elif mode == "check":
        check()
    elif mode == "test":
        test_email()
    else:
        print(__doc__)
        sys.exit(1)
