"""Notifiche opzionali: Telegram o webhook generico a fine esecuzione."""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .config import Settings

LOG = logging.getLogger("lifezen.notify")


def send_telegram(settings: Settings, text: str, session: Optional[requests.Session] = None) -> bool:
    if not (settings.telegram_token and settings.telegram_chat):
        return False
    session = session or requests.Session()
    try:
        response = session.post(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            json={"chat_id": settings.telegram_chat, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": False},
            timeout=30,
        )
        if response.status_code >= 400:
            LOG.warning("Telegram ha risposto %s: %s", response.status_code, response.text[:200])
            return False
        return True
    except requests.RequestException as exc:
        LOG.warning("Invio Telegram fallito: %s", exc)
        return False


def send_webhook(settings: Settings, payload: dict, session: Optional[requests.Session] = None) -> bool:
    if not settings.webhook_url:
        return False
    session = session or requests.Session()
    try:
        response = session.post(settings.webhook_url, json=payload, timeout=30)
        return response.status_code < 400
    except requests.RequestException as exc:
        LOG.warning("Invio webhook fallito: %s", exc)
        return False


def notify(settings: Settings, payload: dict, text: str,
           session: Optional[requests.Session] = None) -> None:
    """Prova tutti i canali configurati; non solleva mai eccezioni."""
    send_telegram(settings, text, session)
    send_webhook(settings, payload, session)


def format_run_report(date: str, status: str, details: dict) -> str:
    lines = [f"<b>myLifeZen</b> — {date}", f"Stato: {status}"]
    for key, value in details.items():
        if value in (None, ""):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def format_manifest(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2)
