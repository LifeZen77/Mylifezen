"""Configurazione: variabili d'ambiente, file .env e percorsi del progetto."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GRAPH_VERSION = "v25.0"
# Versioni considerate valide: se quella scelta non è disponibile lato Meta,
# il client riprova automaticamente con la prima funzionante dell'elenco.
GRAPH_VERSION_FALLBACKS = ["v25.0", "v23.0", "v21.0", "v20.0"]

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def load_dotenv(path: Optional[Path] = None) -> Dict[str, str]:
    """Carica un file .env senza dipendenze esterne.

    Le variabili già presenti nell'ambiente hanno la precedenza (utile in CI).
    """
    loaded: Dict[str, str] = {}
    candidates = [path] if path else [REPO_ROOT / ".env", Path.cwd() / ".env"]
    for candidate in candidates:
        if not candidate or not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = _ENV_LINE.match(line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            value = value.replace("\\n", "\n")
            loaded[key] = value
            os.environ.setdefault(key, value)
    return loaded


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "si", "sì"}


@dataclass
class Settings:
    """Tutta la configurazione del progetto in un unico posto."""

    # --- Instagram -----------------------------------------------------
    ig_user_id: str = ""
    ig_token: str = ""
    app_id: str = ""
    app_secret: str = ""
    graph_version: str = DEFAULT_GRAPH_VERSION

    # --- Hosting immagine (Instagram richiede un URL pubblico) ----------
    image_host: str = "github"          # github | cloudinary | imgbb | dir | none
    published_dir: str = "published"
    image_branch: str = "main"
    cdn: str = "jsdelivr"               # jsdelivr | raw
    public_base_url: str = ""           # per host "dir"
    repo: str = ""                      # owner/name, per host "github"
    github_token: str = ""

    cloudinary_cloud: str = ""
    cloudinary_key: str = ""
    cloudinary_secret: str = ""
    cloudinary_preset: str = ""

    imgbb_key: str = ""

    # --- Comportamento --------------------------------------------------
    timezone: str = "Europe/Rome"
    dry_run: bool = False
    allow_caption_trim: bool = True
    caption_limit: int = 2200           # limite Instagram
    cta_site: str = ""
    telegram_token: str = ""
    telegram_chat: str = ""
    webhook_url: str = ""

    repo_root: Path = field(default_factory=lambda: REPO_ROOT)
    # Percorsi espliciti: utili nei test e per esecuzioni isolate
    state_path: Optional[Path] = None
    output_path: Optional[Path] = None
    env_loaded: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def content_dir(self) -> Path:
        return self.repo_root / "assets" / "content"

    @property
    def fonts_dir(self) -> Path:
        return self.repo_root / "assets" / "fonts"

    @property
    def output_dir(self) -> Path:
        return Path(self.output_path) if self.output_path else self.repo_root / "output"

    @property
    def published_path(self) -> Path:
        return self.repo_root / self.published_dir

    @property
    def state_file(self) -> Path:
        return Path(self.state_path) if self.state_path else self.repo_root / "data" / "state.json"

    @property
    def graph_base(self) -> str:
        return f"https://graph.facebook.com/{self.graph_version}"

    def graph_base_with(self, version: str) -> str:
        return f"https://graph.facebook.com/{version}"

    # ------------------------------------------------------------------
    def missing_for_publish(self) -> list:
        """Ritorna la lista di credenziali mancanti per pubblicare."""
        missing = []
        if not self.ig_user_id:
            missing.append("IG_USER_ID (Instagram Business Account ID)")
        if not self.ig_token:
            missing.append("IG_ACCESS_TOKEN (token di accesso)")
        return missing

    def image_host_ready(self) -> tuple:
        host = self.image_host
        if host in ("github", "jsdelivr", "raw"):
            if not self.repo:
                return False, "manca LIFEZEN_REPO (es. LifeZen77/Mylifezen)"
            if not self.github_token:
                return False, "manca GITHUB_TOKEN / GH_TOKEN con permesso contents:write"
        elif host == "cloudinary":
            if not self.cloudinary_cloud or not (self.cloudinary_preset or (self.cloudinary_key and self.cloudinary_secret)):
                return False, "mancano CLOUDINARY_CLOUD_NAME e (CLOUDINARY_UPLOAD_PRESET oppure API key+secret)"
        elif host == "imgbb":
            if not self.imgbb_key:
                return False, "manca IMGBB_API_KEY"
        elif host == "dir":
            if not self.public_base_url:
                return False, "manca PUBLIC_BASE_URL per l'host 'dir'"
        elif host == "none":
            return True, ""
        else:
            return False, f"host immagini sconosciuto: {host!r}"
        return True, ""

    def as_public_dict(self) -> Dict[str, str]:
        """Configurazione senza segreti, per diagnostica e log."""
        return {
            "graph_version": self.graph_version,
            "ig_user_id": _mask(self.ig_user_id, keep=4),
            "ig_token": _mask(self.ig_token, keep=4),
            "app_id": _mask(self.app_id, keep=4),
            "app_secret": "impostato" if self.app_secret else "—",
            "image_host": self.image_host,
            "repo": self.repo or "—",
            "image_branch": self.image_branch,
            "cdn": self.cdn,
            "timezone": self.timezone,
            "published_dir": self.published_dir,
            "dry_run": str(self.dry_run),
        }


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return "—"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]} ({len(value)} char)"


def load_settings(**overrides) -> Settings:
    """Costruisce le impostazioni da .env + ambiente, con override espliciti."""
    loaded = load_dotenv()

    repo = _env("LIFEZEN_REPO", "GITHUB_REPOSITORY", default="LifeZen77/Mylifezen")

    settings = Settings(
        ig_user_id=_env("IG_USER_ID", "INSTAGRAM_USER_ID", "IG_BUSINESS_ID"),
        ig_token=_env("IG_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN", "IG_TOKEN"),
        app_id=_env("IG_APP_ID", "FB_APP_ID", "META_APP_ID", "INSTAGRAM_APP_ID"),
        app_secret=_env("IG_APP_SECRET", "FB_APP_SECRET", "META_APP_SECRET", "INSTAGRAM_APP_SECRET"),
        graph_version=_env("IG_GRAPH_VERSION", default=DEFAULT_GRAPH_VERSION),
        image_host=_env("LIFEZEN_IMAGE_HOST", "IMAGE_HOST", default="github").lower(),
        published_dir=_env("LIFEZEN_PUBLISHED_DIR", default="published").strip("/"),
        image_branch=_env("LIFEZEN_IMAGE_BRANCH", default="main"),
        cdn=_env("LIFEZEN_CDN", default="jsdelivr").lower(),
        public_base_url=_env("PUBLIC_BASE_URL", "LIFEZEN_PUBLIC_BASE_URL").rstrip("/"),
        repo=repo,
        github_token=_env("GITHUB_TOKEN", "GH_TOKEN", "LIFEZEN_GITHUB_TOKEN"),
        cloudinary_cloud=_env("CLOUDINARY_CLOUD_NAME"),
        cloudinary_key=_env("CLOUDINARY_API_KEY"),
        cloudinary_secret=_env("CLOUDINARY_API_SECRET"),
        cloudinary_preset=_env("CLOUDINARY_UPLOAD_PRESET"),
        imgbb_key=_env("IMGBB_API_KEY"),
        timezone=_env("LIFEZEN_TIMEZONE", default="Europe/Rome"),
        dry_run=_bool(_env("LIFEZEN_DRY_RUN", default="0")),
        cta_site=_env("LIFEZEN_CTA_SITE"),
        telegram_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat=_env("TELEGRAM_CHAT_ID"),
        webhook_url=_env("LIFEZEN_WEBHOOK_URL"),
        env_loaded=loaded,
    )

    for key, value in overrides.items():
        if value is not None and hasattr(settings, key):
            setattr(settings, key, value)
    return settings
