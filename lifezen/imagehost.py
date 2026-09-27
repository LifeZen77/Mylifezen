"""Hosting delle immagini: Instagram pubblica solo da URL pubblico.

Backend disponibili:
  github     -> commit dei JPEG nel repo (CDN jsDelivr o raw.githubusercontent)
  cloudinary -> upload semplice (unsigned preset o firma HMAC)
  imgbb      -> upload semplice con chiave API
  dir        -> solo dry-run: serve un PUBLIC_BASE_URL già configurato
  none       -> nessun upload (usato con --dry-run)
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

from .config import Settings

LOG = logging.getLogger("lifezen.host")

GITHUB_API = "https://api.github.com"


class HostError(RuntimeError):
    pass


@dataclass
class UploadedImage:
    url: str
    alt_url: str = ""
    backend: str = ""
    remote_path: str = ""


def _upload_name(path: Path, date: Optional[dt.date]) -> str:
    """Nome file pubblico, senza duplicare la data già presente nello stem."""
    prefix = date.isoformat() if date else dt.date.today().isoformat()
    stem = path.stem
    if stem.startswith(prefix):
        return f"{stem}.jpg"
    return f"{prefix}-{stem}.jpg"


class ImageHost:
    """Facciata unica sui diversi backend."""

    def __init__(self, settings: Settings, session: Optional[requests.Session] = None):
        self.settings = settings
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    def upload(self, path: Path, date: Optional[dt.date] = None,
               alt_urls: Optional[list] = None) -> UploadedImage:
        path = Path(path)
        if not path.is_file():
            raise HostError(f"Immagine inesistente: {path}")

        host = self.settings.image_host
        if host in ("none", "dir") and self.settings.dry_run:
            return UploadedImage(url=f"file://{path}", backend=host)

        if host == "github":
            return self._upload_github(path, date, alt_urls)
        if host == "cloudinary":
            return self._upload_cloudinary(path, date)
        if host == "imgbb":
            return self._upload_imgbb(path, date)
        if host == "dir":
            return self._upload_directory(path, date)
        if host == "none":
            raise HostError("LIFEZEN_IMAGE_HOST=none non consente la pubblicazione reale.")
        raise HostError(f"Backend immagini non supportato: {host}")

    # ------------------------------------------------------------------
    def _upload_directory(self, path: Path, date: Optional[dt.date]) -> UploadedImage:
        """Copia in una cartella servita da un web server esistente."""
        base = self.settings.public_base_url
        if not base:
            raise HostError("PUBLIC_BASE_URL non configurato per LIFEZEN_IMAGE_HOST=dir.")
        target_dir = Path(self.settings.published_path) / (date.strftime("%Y/%m") if date else "misc")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        target.write_bytes(path.read_bytes())
        rel = target.relative_to(self.settings.published_path)
        return UploadedImage(url=f"{base}/{quote(str(rel))}", backend="dir", remote_path=str(rel))

    # ------------------------------------------------------------------
    def _upload_github(self, path: Path, date: Optional[dt.date],
                       alt_urls: Optional[list] = None) -> UploadedImage:
        s = self.settings
        if not s.repo or not s.github_token:
            raise HostError("Servono LIFEZEN_REPO e GITHUB_TOKEN per pubblicare le immagini su GitHub.")

        year_month = date.strftime("%Y/%m") if date else "misc"
        remote_path = f"{s.published_dir}/{year_month}/{_upload_name(path, date)}"
        api_url = f"{GITHUB_API}/repos/{s.repo}/contents/{quote(remote_path)}"
        headers = {
            "Authorization": f"Bearer {s.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        content = base64.b64encode(path.read_bytes()).decode("ascii")

        payload = {
            "message": f"chore(published): card {remote_path.split('/')[-1]}",
            "content": content,
            "branch": s.image_branch,
        }
        # Se il file esiste già, GitHub richiede lo sha per sovrascrivere.
        existing = self.session.get(api_url, headers=headers,
                                    params={"ref": s.image_branch}, timeout=30)
        if existing.status_code == 200:
            sha = existing.json().get("sha")
            if sha:
                payload["sha"] = sha

        response = self.session.put(api_url, headers=headers, json=payload, timeout=120)
        if response.status_code in (401, 403):
            raise HostError(
                "GitHub ha rifiutato il commit dell'immagine (token senza permesso contents:write)."
            )
        if response.status_code >= 400:
            raise HostError(f"Upload su GitHub fallito: {response.status_code} {response.text[:200]}")

        jsdelivr = f"https://cdn.jsdelivr.net/gh/{s.repo}@{s.image_branch}/{remote_path}"
        raw = f"https://raw.githubusercontent.com/{s.repo}/{s.image_branch}/{remote_path}"
        url, alt = (jsdelivr, raw) if s.cdn != "raw" else (raw, jsdelivr)

        urls = [url, alt] if alt else [url]
        if alt_urls:
            urls.extend(u for u in alt_urls if u not in urls)
        LOG.info("Immagine pubblicata su GitHub: %s", remote_path)
        return UploadedImage(url=url, alt_url=alt, backend="github", remote_path=remote_path)

    # ------------------------------------------------------------------
    def _upload_cloudinary(self, path: Path, date: Optional[dt.date]) -> UploadedImage:
        s = self.settings
        if not s.cloudinary_cloud:
            raise HostError("CLOUDINARY_CLOUD_NAME mancante.")
        endpoint = f"https://api.cloudinary.com/v1_1/{s.cloudinary_cloud}/image/upload"
        public_id = f"lifezen/{_upload_name(path, date)}".replace(".jpg", "")

        files = {"file": (path.name, path.read_bytes(), "image/jpeg")}
        data = {"public_id": public_id}

        if s.cloudinary_preset:
            data["upload_preset"] = s.cloudinary_preset
        elif s.cloudinary_key and s.cloudinary_secret:
            timestamp = int(time.time())
            to_sign = f"public_id={public_id}&timestamp={timestamp}{s.cloudinary_secret}"
            data.update({
                "api_key": s.cloudinary_key,
                "timestamp": timestamp,
                "signature": hashlib.sha1(to_sign.encode()).hexdigest(),
            })
        else:
            raise HostError("Serve CLOUDINARY_UPLOAD_PRESET oppure API key + secret.")

        response = self.session.post(endpoint, data=data, files=files, timeout=120)
        if response.status_code >= 400:
            raise HostError(f"Cloudinary: {response.status_code} {response.text[:200]}")
        payload = response.json()
        return UploadedImage(url=payload["secure_url"], backend="cloudinary",
                             remote_path=payload.get("public_id", ""))

    # ------------------------------------------------------------------
    def _upload_imgbb(self, path: Path, date: Optional[dt.date]) -> UploadedImage:
        s = self.settings
        if not s.imgbb_key:
            raise HostError("IMGBB_API_KEY mancante.")
        response = self.session.post(
            "https://api.imgbb.com/1/upload",
            params={"key": s.imgbb_key},
            files={"image": (path.name, path.read_bytes(), "image/jpeg")},
            timeout=120,
        )
        if response.status_code >= 400:
            raise HostError(f"ImgBB: {response.status_code} {response.text[:200]}")
        payload = response.json()
        if not payload.get("success"):
            raise HostError(f"ImgBB ha risposto: {json.dumps(payload)[:200]}")
        data = payload["data"]
        return UploadedImage(url=data["url"], alt_url=data.get("display_url", ""),
                             backend="imgbb", remote_path=data.get("id", ""))

    # ------------------------------------------------------------------
    def check_remote(self, url: str, timeout: int = 20) -> bool:
        """Conferma che l'immagine sia raggiungibile pubblicamente prima di pubblicare."""
        if url.startswith("file://"):
            return True
        try:
            response = self.session.get(url, timeout=timeout, stream=True)
            ok = response.status_code == 200 and "image" in response.headers.get("Content-Type", "")
            response.close()
            return ok
        except requests.RequestException as exc:
            LOG.debug("Verifica URL fallita (%s): %s", url, exc)
            return False
