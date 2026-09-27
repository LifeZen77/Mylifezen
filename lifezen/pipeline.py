"""Pipeline giornaliera: contenuto -> card -> upload -> pubblicazione."""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .card import render_card, render_story
from .config import Settings, load_settings
from .content import DayContent, Library, build_caption, day_of_year, load_library
from .imagehost import HostError, ImageHost
from .instagram import InstagramClient, InstagramError
from .notify import format_run_report, notify
from .state import State

LOG = logging.getLogger("lifezen.pipeline")


def relative_to(path: Optional[Path], base: Path) -> str:
    """Percorso relativo se possibile, altrimenti assoluto (cartelle isolate nei test)."""
    if not path:
        return ""
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return str(path)


def today_in(settings: Settings, override: Optional[dt.date] = None) -> dt.date:
    if override:
        return override
    try:
        return dt.datetime.now(ZoneInfo(settings.timezone)).date()
    except Exception:
        return dt.date.today()


@dataclass
class DayPlan:
    """Tutto ciò che serve per il post di un giorno."""

    date: dt.date
    entry: DayContent
    caption: str
    image_path: Path
    image_url: str = ""
    alt_urls: List[str] = field(default_factory=list)
    story_path: Optional[Path] = None
    status: str = "planned"
    media_id: str = ""
    permalink: str = ""
    message: str = ""
    already_published: bool = False

    @property
    def day_number(self) -> int:
        return day_of_year(self.date)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "day": self.day_number,
            "type": self.entry.type,
            "title": self.entry.title,
            "status": self.status,
            "media_id": self.media_id,
            "permalink": self.permalink,
            "message": self.message,
            "image": str(self.image_path),
            "story": str(self.story_path) if self.story_path else None,
            "image_url": self.image_url,
        }

    def save_manifest(self, settings: Settings) -> Path:
        target = settings.output_dir / "manifests" / f"{self.date.isoformat()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def build_day(settings: Settings, library: Library, date: dt.date, *,
              with_story: bool = False, force: bool = False) -> DayPlan:
    """Genera contenuto, caption e immagine per una data."""
    entry = library.get_by_date(date)
    caption = build_caption(entry, library, date, cta_site=settings.cta_site,
                            limit=settings.caption_limit)
    image_path = settings.output_dir / "cards" / f"{date.isoformat()}-{entry.type}.jpg"
    render_card(entry, library, date, image_path, fonts_dir=settings.fonts_dir)

    story_path = None
    if with_story:
        story_path = settings.output_dir / "stories" / f"{date.isoformat()}-{entry.type}-story.jpg"
        render_story(entry, library, date, story_path, fonts_dir=settings.fonts_dir)

    plan = DayPlan(date=date, entry=entry, caption=caption, image_path=image_path,
                   story_path=story_path)
    if not force and State(settings.state_file).is_published(date):
        plan.already_published = True
        plan.status = "già pubblicato"
    return plan


def publish_day(settings: Settings, library: Library, date: dt.date, *, force: bool = False,
                with_story: bool = False, dry_run: Optional[bool] = None,
                client: Optional[InstagramClient] = None,
                host: Optional[ImageHost] = None) -> DayPlan:
    """Esegue l'intero ciclo per un giorno e ritorna il piano aggiornato."""
    dry_run = settings.dry_run if dry_run is None else dry_run
    state = State(settings.state_file)

    if not force and state.is_published(date):
        record = state.published_record(date) or {}
        plan = build_day(settings, library, date, with_story=False, force=True)
        plan.status = "saltato (già pubblicato)"
        plan.already_published = True
        plan.media_id = record.get("media_id", "")
        plan.permalink = record.get("permalink", "")
        LOG.info("%s: già pubblicato (media %s) — uso --force per ripubblicare.",
                 date.isoformat(), plan.media_id)
        plan.save_manifest(settings)
        return plan

    plan = build_day(settings, library, date, with_story=with_story, force=True)
    LOG.info("%s — %s (giorno %s/365): card generata in %s",
             date.isoformat(), plan.entry.title or plan.entry.type, plan.day_number, plan.image_path)

    if dry_run:
        plan.status = "dry-run"
        plan.message = "Nessuna pubblicazione: modalità dry-run."
        state.record_run({"date": date.isoformat(), "status": "dry-run", "type": plan.entry.type})
        plan.save_manifest(settings)
        return plan

    missing = settings.missing_for_publish()
    if missing:
        raise HostError("Configurazione incompleta per pubblicare: " + "; ".join(missing))

    ready, reason = settings.image_host_ready()
    if not ready:
        raise HostError(f"Host immagini non pronto: {reason}")

    host = host or ImageHost(settings)
    client = client or InstagramClient(settings)

    uploaded = host.upload(plan.image_path, date)
    plan.image_url = uploaded.url
    plan.alt_urls = [uploaded.alt_url] if uploaded.alt_url else []
    LOG.info("Immagine disponibile su %s (%s)", uploaded.url, uploaded.backend)

    if uploaded.backend != "dir" and not host.check_remote(uploaded.url):
        if uploaded.alt_url and host.check_remote(uploaded.alt_url):
            plan.alt_urls, uploaded.url = [uploaded.url], uploaded.alt_url
            plan.image_url = uploaded.url
            LOG.warning("CDN non raggiungibile: uso %s", uploaded.url)
        else:
            LOG.warning("URL immagine non verificabile pubblicamente: proseguo comunque.")

    try:
        result = client.publish_photo(plan.image_url, plan.caption,
                                      alt_text=f"{plan.entry.type}: {plan.entry.title}".strip(": "))
    except InstagramError as exc:
        plan.status = "errore"
        plan.message = str(exc)
        state.record_run({"date": date.isoformat(), "status": "errore", "message": str(exc),
                          "image_url": plan.image_url})
        plan.save_manifest(settings)
        raise

    plan.status = "pubblicato"
    plan.media_id = result.media_id
    plan.permalink = result.permalink
    plan.message = f"Graph API {result.version}"

    state.record_publish(date, {
        "media_id": result.media_id,
        "creation_id": result.creation_id,
        "permalink": result.permalink,
        "type": plan.entry.type,
        "title": plan.entry.title,
        "image_url": plan.image_url,
        "image_path": relative_to(plan.image_path, settings.repo_root),
        "story": relative_to(plan.story_path, settings.repo_root),
    })
    state.record_run({"date": date.isoformat(), "status": "pubblicato",
                      "media_id": result.media_id, "type": plan.entry.type})
    plan.save_manifest(settings)
    LOG.info("Pubblicato: %s%s", result.media_id,
             f" — {result.permalink}" if result.permalink else "")
    return plan


def run_for_date(settings: Settings, library: Library, date: dt.date, *, force: bool = False,
                 with_story: bool = False, dry_run: Optional[bool] = None) -> DayPlan:
    """Wrapper con notifica di esito e manifest salvato."""
    try:
        plan = publish_day(settings, library, date, force=force, with_story=with_story,
                           dry_run=dry_run)
        details = {
            "Tipo": plan.entry.type,
            "Titolo": plan.entry.title,
            "Immagine": plan.image_path.name,
            "Media ID": plan.media_id,
            "Link": plan.permalink,
            "Nota": plan.message,
        }
        notify(settings, {"date": date.isoformat(), "status": plan.status, **details},
               format_run_report(date.isoformat(), plan.status, details))
    except Exception as exc:  # notifica anche in caso di errore, poi rilancia
        notify(settings, {"date": date.isoformat(), "status": "errore", "error": str(exc)},
               format_run_report(date.isoformat(), "errore", {"Dettaglio": str(exc)}))
        raise
    return plan


def load_all(settings: Optional[Settings] = None):
    """Scorciatoia: settings + library già caricate."""
    settings = settings or load_settings()
    return settings, load_library(settings.content_dir)


def month_dates(year: int, month: int) -> List[dt.date]:
    first = dt.date(year, month, 1)
    next_month = dt.date(year + (month == 12), (month % 12) + 1, 1)
    days = (next_month - first).days
    return [first + dt.timedelta(days=offset) for offset in range(days)]


def plan_month(settings: Settings, library: Library, year: int, month: int,
               *, with_story: bool = False) -> List[DayPlan]:
    dates = month_dates(year, month)
    return [build_day(settings, library, date, with_story=with_story) for date in dates]


def summary(plans: List[DayPlan]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    return counts
