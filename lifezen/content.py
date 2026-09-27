"""Libreria editoriale: caricamento dei 365 giorni e composizione delle caption."""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


class ContentError(RuntimeError):
    """Errore nella libreria dei contenuti."""


def slugify(value: str, max_len: int = 48) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:max_len].strip("-") or "lifezen"


@dataclass
class DayContent:
    """Un singolo giorno del calendario editoriale."""

    month: int
    day: int
    type: str
    title: str
    text: str
    caption: str
    tags: List[str] = field(default_factory=list)
    theme: str = ""
    month_name: str = ""

    # ------------------------------------------------------------------
    @property
    def text_lines(self) -> List[str]:
        return [line.strip() for line in self.text.split("\n") if line.strip()]

    def key(self) -> Tuple[int, int]:
        return (self.month, self.day)

    def label(self, library: "Library") -> str:
        return library.type_label(self.type)

    def slug(self) -> str:
        return slugify(self.title or self.text_lines[0] if self.text_lines else "lifezen")


class Library:
    """Collezione dei contenuti indicizzata per (mese, giorno)."""

    def __init__(self, entries: Dict[Tuple[int, int], DayContent], meta: dict):
        self.entries = entries
        self.meta = meta
        self.brand = meta.get("brand", {})
        self.types: Dict[str, dict] = meta.get("types", {})
        self.hashtags: dict = meta.get("hashtags", {})
        self.months: Dict[int, dict] = meta.get("months", {})
        self.bonus: Optional[DayContent] = None
        if "bonus" in meta:
            bonus = meta["bonus"]
            self.bonus = DayContent(
                month=2, day=29, type=bonus.get("type", "pensiero"),
                title=bonus.get("title", "Il giorno in più"),
                text=bonus.get("text", ""), caption=bonus.get("caption", ""),
                tags=bonus.get("tags", []), theme="Il giorno in più",
                month_name="febbraio",
            )

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.entries)

    def type_label(self, type_key: str) -> str:
        return self.types.get(type_key, {}).get("label", type_key.upper())

    def type_cta(self, type_key: str) -> str:
        return self.types.get(type_key, {}).get("cta", "")

    def month_theme(self, month: int) -> str:
        return self.months.get(str(month), {}).get("theme", "")

    def month_name(self, month: int) -> str:
        return self.months.get(str(month), {}).get("name", MESI[month - 1].capitalize())

    # ------------------------------------------------------------------
    def get(self, month: int, day: int) -> DayContent:
        if (month, day) in self.entries:
            return self.entries[(month, day)]
        if month == 2 and day == 29 and self.bonus:
            return self.bonus
        raise ContentError(
            f"Testo non trovato per il {day:02d}/{month:02d}. "
            f"La libreria contiene {len(self.entries)} giorni: controlla assets/content/."
        )

    def get_by_date(self, date: dt.date) -> DayContent:
        return self.get(date.month, date.day)

    def all_entries(self) -> List[DayContent]:
        return [self.entries[key] for key in sorted(self.entries)]

    # ------------------------------------------------------------------
    def hashtags_for(self, entry: DayContent) -> List[str]:
        base = list(self.hashtags.get("base", []))
        per_theme = self.hashtags.get("themes", {}).get(slugify(entry.theme), [])
        extras = [tag_to_hashtag(tag, self.hashtags.get("tag_map", {})) for tag in entry.tags]
        ordered: List[str] = []
        for tag in base + list(per_theme) + extras:
            tag = tag if tag.startswith("#") else f"#{tag}"
            if tag not in ordered and _valid_hashtag(tag):
                ordered.append(tag)
        return ordered[: self.hashtags.get("max", 15)]


_INVALID_HASHTAG = re.compile(r"[\s#\-\.,!?'\"()\[\]]")


def _valid_hashtag(tag: str) -> bool:
    """Instagram: nessuno spazio, nessun trattino, niente punteggiatura."""
    body = tag.lstrip("#")
    return len(body) > 2 and not _INVALID_HASHTAG.search(body)


def tag_to_hashtag(tag: str, tag_map: Optional[Dict[str, str]] = None) -> str:
    """Trasforma un'etichetta editoriale in un hashtag valido per Instagram.

    Instagram accetta solo lettere, numeri e underscore: niente spazi,
    accenti o trattini. Le etichette ricorrenti si mappano a mano in
    common.json (tag_map) per restare leggibili.
    """
    tag = tag.strip()
    if not tag:
        return ""
    if tag.startswith("#"):
        return tag
    tag_map = tag_map or {}
    key = tag.lower()
    if key in tag_map:
        mapped = tag_map[key]
        return mapped if mapped.startswith("#") else f"#{mapped}"

    ascii_tag = unicodedata.normalize("NFKD", tag).encode("ascii", "ignore").decode("ascii")
    words = [w for w in re.split(r"\s+", ascii_tag) if w]
    return "#" + "".join(words).lower()


def load_library(content_dir: Path) -> Library:
    """Legge month-XX.json + common.json e costruisce la libreria."""
    if not content_dir.is_dir():
        raise ContentError(f"Cartella contenuti non trovata: {content_dir}")

    common_path = content_dir / "common.json"
    if not common_path.is_file():
        raise ContentError(f"File di configurazione mancante: {common_path}")
    meta = json.loads(common_path.read_text(encoding="utf-8"))

    entries: Dict[Tuple[int, int], DayContent] = {}
    for path in sorted(content_dir.glob("month-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        month = int(data.get("month", 0))
        if not 1 <= month <= 12:
            raise ContentError(f"{path.name}: campo 'month' non valido ({month})")
        for raw in data.get("days", []):
            day = int(raw["day"])
            entry = DayContent(
                month=month,
                day=day,
                type=raw.get("type", "pensiero"),
                title=raw.get("title", ""),
                text=raw["text"].strip(),
                caption=raw.get("caption", "").strip(),
                tags=list(raw.get("tags", [])),
                theme=data.get("theme", ""),
                month_name=data.get("name", MESI[month - 1].capitalize()),
            )
            if entry.key() in entries:
                raise ContentError(f"{path.name}: giorno duplicato {day:02d}/{month:02d}")
            entries[entry.key()] = entry

    meta["months"] = _months_meta(content_dir, meta)
    return Library(entries, meta)


def _months_meta(content_dir: Path, meta: dict) -> dict:
    months = dict(meta.get("months", {}))
    for path in sorted(content_dir.glob("month-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        month = str(int(data.get("month", 0)))
        months.setdefault(month, {})
        months[month].update({
            "name": data.get("name", months[month].get("name", "")),
            "theme": data.get("theme", months[month].get("theme", "")),
        })
    return months


def day_of_year(date: dt.date) -> int:
    return date.timetuple().tm_yday


def human_date(date: dt.date) -> str:
    return f"{GIORNI[date.weekday()]} {date.day} {MESI[date.month - 1]} {date.year}"


def short_date(date: dt.date) -> str:
    return f"{date.day:02d} · {date.month:02d}"


def fit_caption(caption: str, limit: int = 2200) -> str:
    """Accorcia la caption mantenendo hashtag e struttura se supera il limite IG."""
    if len(caption) <= limit:
        return caption
    lines = caption.split("\n")
    tags = []
    while lines and lines[-1].strip().startswith("#"):
        tags.insert(0, lines.pop())
    body = "\n".join(lines).rstrip()
    tags_block = "\n".join(tags)
    budget = limit - len(tags_block) - 24
    if budget < 120:
        return (body[: limit - 4] + " …")[:limit]
    trimmed = body[:budget].rsplit("\n", 1)[0].rstrip()
    return f"{trimmed}\n…\n{tags_block}".strip()


def build_caption(entry: DayContent, library: Library, date: dt.date,
                  cta_site: str = "", limit: int = 2200) -> str:
    """Compone la caption Instagram: gancio, testo, invito, firma, hashtag."""
    brand = library.brand
    handle = brand.get("handle", "@lifezen77real")
    name = brand.get("name", "myLifeZen")

    parts: List[str] = []
    if entry.title:
        parts.append(f"{entry.title.strip()}")
    parts.append(entry.text.strip())
    if entry.caption:
        parts.append(entry.caption.strip())

    cta = library.type_cta(entry.type)
    if cta:
        parts.append(f"{cta}")

    footer = [f"{brand.get('ornament', '✦')} {name} — {brand.get('tagline', '365 giorni di zen')}"]
    footer.append(f"Giorno {day_of_year(date)}/365 · tema del mese: {library.month_theme(entry.month)}")
    if cta_site:
        footer.append(f"🔗 {cta_site}")
    footer.append(f"Salva il post ✦ Segui {handle} per non perdere il pensiero di domani")
    parts.append("\n".join(footer))

    body = "\n\n".join(p for p in parts if p)
    hashtags = " ".join(library.hashtags_for(entry))
    caption = f"{body}\n\n{hashtags}".strip()
    return fit_caption(caption, limit)


def caption_preview(caption: str) -> str:
    """Versione leggibile a terminale."""
    return re.sub(r"\n{3,}", "\n\n", caption)
