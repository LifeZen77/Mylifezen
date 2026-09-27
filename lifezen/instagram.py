"""Client Instagram Graph API: creazione container e pubblicazione.

Flusso ufficiale (Content Publishing):
  1. POST /{ig-user-id}/media      -> creation_id
  2. (attesa che il container sia FINISHED)
  3. POST /{ig-user-id}/media_publish con creation_id
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from .config import GRAPH_VERSION_FALLBACKS, Settings

LOG = logging.getLogger("lifezen.instagram")

API_ERROR = "https://developers.facebook.com/docs/instagram-platform/content-publishing"


class InstagramError(RuntimeError):
    """Errore restituito dalla Graph API, con messaggio leggibile."""

    def __init__(self, message: str, *, code: Optional[int] = None, subcode: Optional[int] = None,
                 payload: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.payload = payload or {}

    @property
    def is_token_problem(self) -> bool:
        return self.code in {190, 102, 467, 463}

    @property
    def is_rate_limit(self) -> bool:
        return self.code in {4, 17, 32, 613}


@dataclass
class PublishResult:
    media_id: str
    creation_id: str
    permalink: str = ""
    version: str = ""


class InstagramClient:
    """Wrapper minimale e tollerante sulla Graph API."""

    def __init__(self, settings: Settings, session: Optional[requests.Session] = None,
                 timeout: int = 60):
        self.settings = settings
        self.session = session or requests.Session()
        self.timeout = timeout
        self.version = settings.graph_version
        self._version_verified = False

    # ------------------------------------------------------------------
    def _url(self, path: str, version: Optional[str] = None) -> str:
        base = self.settings.graph_base_with(version or self.version)
        return f"{base}/{path.lstrip('/')}"

    def _handle_error(self, response: requests.Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            raise InstagramError(f"HTTP {response.status_code}: {response.text[:300]}")
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message", response.text[:300])
        detail = error.get("error_user_msg") or error.get("error_user_title") or ""
        full = f"{message} — {detail}" if detail else message
        raise InstagramError(full, code=error.get("code"), subcode=error.get("error_subcode"),
                             payload=payload)

    def _request(self, method: str, path: str, *, data: Optional[dict] = None,
                 params: Optional[dict] = None, version: Optional[str] = None,
                 retries: int = 3) -> dict:
        data = dict(data or {})
        params = dict(params or {})
        data.setdefault("access_token", self.settings.ig_token)
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                response = self.session.request(
                    method, self._url(path, version), data=data, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = exc
                LOG.warning("Errore di rete (tentativo %s/%s): %s", attempt, retries, exc)
                time.sleep(2 * attempt)
                continue

            if response.status_code >= 400:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                if error.get("is_transient") or response.status_code >= 500:
                    last_error = InstagramError(error.get("message", "errore temporaneo"))
                    LOG.warning("Errore temporaneo Graph API (tentativo %s/%s): %s",
                                attempt, retries, error.get("message"))
                    time.sleep(3 * attempt)
                    continue
                self._handle_error(response)

            try:
                return response.json()
            except ValueError:
                return {}

        if isinstance(last_error, InstagramError):
            raise last_error
        raise InstagramError(f"Richiesta fallita dopo {retries} tentativi: {last_error}")

    # ------------------------------------------------------------------
    def verify_version(self) -> str:
        """Verifica che la versione della Graph API configurata sia attiva.

        Se Meta ha ritirato la versione scelta, prova le alternative note.
        """
        if self._version_verified:
            return self.version
        candidates = [self.version] + [v for v in GRAPH_VERSION_FALLBACKS if v != self.version]
        for candidate in candidates:
            try:
                self._request("GET", self.settings.ig_user_id,
                              params={"fields": "id,username"},
                              version=candidate, retries=1)
                if candidate != self.version:
                    LOG.warning("Versione Graph %s non disponibile: uso %s", self.version, candidate)
                self.version = candidate
                self._version_verified = True
                return candidate
            except InstagramError as exc:
                if exc.is_token_problem:
                    raise
                LOG.debug("Versione %s non utilizzabile: %s", candidate, exc)
                continue
        raise InstagramError(
            "Nessuna versione della Graph API ha risposto. Controlla IG_USER_ID e IG_ACCESS_TOKEN."
        )

    # ------------------------------------------------------------------
    def account_info(self) -> Dict[str, str]:
        return self._request("GET", self.settings.ig_user_id,
                             params={"fields": "id,username,name,followers_count,media_count"})

    def debug_token(self) -> dict:
        if not (self.settings.app_id and self.settings.app_secret):
            raise InstagramError("Servono IG_APP_ID e IG_APP_SECRET per leggere lo stato del token.")
        return self._request(
            "GET", "debug_token",
            params={"input_token": self.settings.ig_token,
                    "access_token": f"{self.settings.app_id}|{self.settings.app_secret}"},
        )

    def check_publish_quota(self) -> dict:
        try:
            return self._request("GET", f"{self.settings.ig_user_id}/content_publishing_limit",
                                 params={"fields": "quota_usage,config"})
        except InstagramError as exc:
            LOG.debug("Quota non disponibile: %s", exc)
            return {}

    # ------------------------------------------------------------------
    def create_container(self, image_url: str, caption: str, *,
                         alt_text: str = "", share_to_feed: bool = True) -> str:
        payload = {
            "image_url": image_url,
            "caption": caption,
        }
        if alt_text:
            payload["alt_text"] = alt_text[:1000]
        if not share_to_feed:
            payload["share_to_feed"] = "false"
        result = self._request("POST", f"{self.settings.ig_user_id}/media", data=payload)
        creation_id = result.get("id")
        if not creation_id:
            raise InstagramError(f"Container senza id: {result}")
        LOG.info("Container creato: %s", creation_id)
        return creation_id

    def container_status(self, creation_id: str) -> str:
        result = self._request("GET", creation_id, params={"fields": "status_code,status"})
        return result.get("status_code", "")

    def wait_for_container(self, creation_id: str, *, timeout: int = 120,
                           interval: float = 4.0) -> str:
        """Attende che il container sia pronto (Instagram scarica l'immagine)."""
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            last = self.container_status(creation_id)
            if last in {"FINISHED", "PUBLISHED"}:
                return last
            if last in {"ERROR", "EXPIRED"}:
                raise InstagramError(f"Container in stato {last}: immagine non raggiungibile o non valida.")
            time.sleep(interval)
        LOG.warning("Container non confermato entro %ss (stato: %s): provo a pubblicare comunque.", timeout, last)
        return last

    def publish(self, creation_id: str) -> str:
        result = self._request("POST", f"{self.settings.ig_user_id}/media_publish",
                               data={"creation_id": creation_id})
        media_id = result.get("id")
        if not media_id:
            raise InstagramError(f"Pubblicazione senza id: {result}")
        return media_id

    def media_permalink(self, media_id: str) -> str:
        try:
            result = self._request("GET", media_id, params={"fields": "permalink,id"})
            return result.get("permalink", "")
        except InstagramError:
            return ""

    # ------------------------------------------------------------------
    def publish_photo(self, image_url: str, caption: str, *, alt_text: str = "",
                      wait_timeout: int = 120) -> PublishResult:
        self.verify_version()
        creation_id = self.create_container(image_url, caption, alt_text=alt_text)
        self.wait_for_container(creation_id, timeout=wait_timeout)
        media_id = self.publish(creation_id)
        return PublishResult(media_id=media_id, creation_id=creation_id,
                             permalink=self.media_permalink(media_id), version=self.version)

    def candidates_for(self, image_url: str) -> List[str]:
        """URL alternativi da provare se Instagram non riesce a scaricare l'immagine."""
        return [image_url]

    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, str]:
        """Diagnostica: versione API, account, quota, scadenza token."""
        report: Dict[str, str] = {}
        version = self.verify_version()
        report["graph_version"] = version
        account = self.account_info()
        report["account"] = f"@{account.get('username', '?')} (id {account.get('id', '?')})"
        report["follower"] = str(account.get("followers_count", "—"))
        report["media"] = str(account.get("media_count", "—"))
        quota = self.check_publish_quota()
        if quota:
            data = quota.get("data", [{}])[0]
            report["quota_24h"] = f"{data.get('quota_usage', '?')}/50"
        try:
            token = self.debug_token().get("data", {})
            if token.get("expires_at"):
                expires = time.strftime("%d/%m/%Y", time.localtime(token["expires_at"]))
                report["token_scade"] = expires
            else:
                report["token_scade"] = "mai (token a lunga durata)"
            report["token_valido"] = "sì" if token.get("is_valid") else "NO"
        except InstagramError as exc:
            report["token_scade"] = f"non verificabile ({exc})"
        return report
