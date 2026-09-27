"""Test end-to-end della pubblicazione con Graph API e hosting simulati.

Verifica l'intero ciclo senza toccare la rete: verifica versione API,
creazione container, attesa FINISHED, media_publish, registrazione stato
e blocco delle doppie pubblicazioni.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import pytest

from lifezen.config import Settings
from lifezen.content import load_library
from lifezen.imagehost import UploadedImage
from lifezen.instagram import InstagramClient, InstagramError
from lifezen.pipeline import publish_day
from lifezen.state import State

REPO = Path(__file__).resolve().parent.parent
CONTENT = REPO / "assets" / "content"


# ---------------------------------------------------------------------------
# Finta Graph API
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)
        self.headers = {"Content-Type": "application/json"}

    def json(self) -> dict:
        return self._payload


class FakeGraphSession:
    """Simula gli endpoint usati dal client Instagram."""

    def __init__(self, *, container_status: str = "FINISHED", fail_publish: bool = False):
        self.calls: List[dict] = []
        self.container_status = container_status
        self.fail_publish = fail_publish
        self.container_payload: dict = {}

    def request(self, method, url, data=None, params=None, timeout=None) -> FakeResponse:
        data = data or {}
        params = params or {}
        self.calls.append({"method": method, "url": url, "data": data, "params": params})
        # da "https://graph.facebook.com/v25.0/creation_1" estrae "creation_1"
        path = urlparse(url).path.strip("/").split("/", 1)[-1]

        # verifica versione / info account
        if method == "GET" and params.get("fields", "").startswith("id,username"):
            return FakeResponse({"id": "17841400000000000", "username": "lifezen77real",
                                 "followers_count": 1234, "media_count": 56})

        if "/media_publish" in url:
            if self.fail_publish:
                return FakeResponse({"error": {"message": "Media già pubblicato",
                                               "code": 9007, "error_subcode": 2207027}}, status=400)
            return FakeResponse({"id": "17900000000000001"})

        # stato container / permalink
        if method == "GET" and path == "creation_1":
            return FakeResponse({"status_code": self.container_status})
        if method == "GET" and path == "17900000000000001":
            return FakeResponse({"id": path, "permalink": "https://www.instagram.com/p/ABC123/"})

        # creazione container
        if method == "POST" and url.endswith("/media"):
            self.container_payload = dict(data)
            return FakeResponse({"id": "creation_1"})

        if "content_publishing_limit" in url:
            return FakeResponse({"data": [{"quota_usage": 1}]})

        if "debug_token" in url:
            return FakeResponse({"data": {"is_valid": True, "expires_at": 1900000000}})

        raise AssertionError(f"Chiamata non simulata: {method} {url} params={params}")


class FakeHost:
    """Host immagini finto: nessun upload reale."""

    def __init__(self, url: str = "https://cdn.jsdelivr.net/gh/LifeZen77/Mylifezen@main/published/x.jpg"):
        self.url = url
        self.uploaded: List[Path] = []

    def upload(self, path: Path, date=None, alt_urls=None) -> UploadedImage:
        self.uploaded.append(Path(path))
        return UploadedImage(url=self.url, alt_url="https://raw.githubusercontent.com/x.jpg",
                             backend="github", remote_path="published/x.jpg")

    def check_remote(self, url: str, timeout: int = 10) -> bool:
        return True


@pytest.fixture(scope="module")
def library():
    return load_library(CONTENT)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = dict(
        repo_root=REPO,
        state_path=tmp_path / "state.json",
        output_path=tmp_path / "output",
        ig_user_id="17841400000000000",
        ig_token="EAAG-token-di-prova",
        app_id="123456",
        app_secret="segretissimo",
        image_host="github",
        repo="LifeZen77/Mylifezen",
        github_token="ghp_finto",
        dry_run=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Client Instagram
# ---------------------------------------------------------------------------

def test_health_check_con_api_simulata(tmp_path: Path):
    settings = make_settings(tmp_path)
    client = InstagramClient(settings, session=FakeGraphSession())
    report = client.health_check()
    assert report["account"] == "@lifezen77real (id 17841400000000000)"
    assert report["token_valido"] == "sì"
    assert report["quota_24h"] == "1/50"


def test_verifica_versione_ripiega_su_alternativa(tmp_path: Path):
    settings = make_settings(tmp_path, graph_version="v99.0")

    class VersionAware(FakeGraphSession):
        def request(self, method, url, data=None, params=None, timeout=None):
            if method == "GET" and params and params.get("fields", "").startswith("id,username"):
                if "/v99.0/" in url:
                    return FakeResponse({"error": {"message": "Unknown path components",
                                                   "code": 2500}}, status=400)
            return super().request(method, url, data, params, timeout)

    client = InstagramClient(settings, session=VersionAware())
    assert client.verify_version() == "v25.0"


def test_caption_trasmessa_a_instagram(tmp_path: Path, library):
    session = FakeGraphSession()
    settings = make_settings(tmp_path)
    client = InstagramClient(settings, session=session)
    date = dt.date(2026, 3, 12)
    library_entry = library.get_by_date(date)
    from lifezen.content import build_caption
    caption = build_caption(library_entry, library, date)

    result = client.publish_photo("https://esempio.it/card.jpg", caption)
    assert result.media_id == "17900000000000001"
    assert result.permalink.endswith("ABC123/")

    container_call = [c for c in session.calls if c["url"].endswith("/media")][0]
    assert container_call["data"]["image_url"] == "https://esempio.it/card.jpg"
    assert container_call["data"]["caption"] == caption
    assert container_call["data"]["access_token"] == settings.ig_token


def test_stato_container_in_errore(tmp_path: Path):
    settings = make_settings(tmp_path)
    client = InstagramClient(settings, session=FakeGraphSession(container_status="ERROR"))
    with pytest.raises(InstagramError) as exc:
        client.publish_photo("https://esempio.it/x.jpg", "prova")
    assert "ERROR" in str(exc.value)


def test_messaggio_errore_leggibile(tmp_path: Path):
    settings = make_settings(tmp_path)
    client = InstagramClient(settings, session=FakeGraphSession(fail_publish=True))
    with pytest.raises(InstagramError) as exc:
        client.publish_photo("https://esempio.it/x.jpg", "prova")
    assert "già pubblicato" in str(exc.value)
    assert exc.value.code == 9007


# ---------------------------------------------------------------------------
# Pipeline completa
# ---------------------------------------------------------------------------

def test_pipeline_completa_pubblica_e_registra(tmp_path: Path, library):
    settings = make_settings(tmp_path)
    session = FakeGraphSession()
    date = dt.date(2026, 5, 9)

    plan = publish_day(settings, library, date,
                       client=InstagramClient(settings, session=session),
                       host=FakeHost())

    assert plan.status == "pubblicato"
    assert plan.media_id == "17900000000000001"
    assert plan.permalink.startswith("https://www.instagram.com/p/")
    assert plan.image_path.is_file()
    assert len(plan.caption) <= 2200

    # lo stato è stato salvato e il contenuto contiene la caption corretta
    state = State(settings.state_file)
    record = state.published_record(date)
    assert record and record["media_id"] == "17900000000000001"
    assert record["type"] == library.get_by_date(date).type

    manifest = settings.output_dir / "manifests" / f"{date.isoformat()}.json"
    assert manifest.is_file()
    assert json.loads(manifest.read_text())["media_id"] == "17900000000000001"


def test_doppia_pubblicazione_bloccata(tmp_path: Path, library):
    settings = make_settings(tmp_path)
    session = FakeGraphSession()
    date = dt.date(2026, 5, 10)

    publish_day(settings, library, date, client=InstagramClient(settings, session=session),
                host=FakeHost())
    calls_after_first = len(session.calls)

    again = publish_day(settings, library, date,
                        client=InstagramClient(settings, session=session), host=FakeHost())
    assert again.already_published
    assert "già pubblicato" in again.status
    assert len(session.calls) == calls_after_first, "non deve chiamare di nuovo l'API"


def test_force_ripubblica(tmp_path: Path, library):
    settings = make_settings(tmp_path)
    session = FakeGraphSession()
    date = dt.date(2026, 5, 11)

    publish_day(settings, library, date, client=InstagramClient(settings, session=session),
                host=FakeHost())
    forced = publish_day(settings, library, date, force=True,
                         client=InstagramClient(settings, session=session), host=FakeHost())
    assert forced.status == "pubblicato"
    assert not forced.already_published


def test_dry_run_non_chiama_instagram(tmp_path: Path, library):
    settings = make_settings(tmp_path, dry_run=True)
    session = FakeGraphSession()
    plan = publish_day(settings, library, dt.date(2026, 5, 12),
                       client=InstagramClient(settings, session=session), host=FakeHost())
    assert plan.status == "dry-run"
    assert session.calls == [], "in dry-run nessuna chiamata deve partire"


def test_credenziali_mancanti_danno_errore_chiaro(tmp_path: Path, library):
    settings = make_settings(tmp_path, ig_user_id="", ig_token="")
    with pytest.raises(Exception) as exc:
        publish_day(settings, library, dt.date(2026, 5, 13), host=FakeHost())
    assert "IG_USER_ID" in str(exc.value)


def test_story_generata_insieme_alla_card(tmp_path: Path, library):
    from PIL import Image

    settings = make_settings(tmp_path)
    plan = publish_day(settings, library, dt.date(2026, 5, 14), with_story=True,
                       client=InstagramClient(settings, session=FakeGraphSession()),
                       host=FakeHost())
    assert plan.story_path and plan.story_path.is_file()
    with Image.open(plan.story_path) as image:
        assert image.size == (1080, 1920)


def test_errore_instagram_non_registra_pubblicazione(tmp_path: Path, library):
    settings = make_settings(tmp_path)
    date = dt.date(2026, 5, 15)
    with pytest.raises(InstagramError):
        publish_day(settings, library, date,
                    client=InstagramClient(settings, session=FakeGraphSession(fail_publish=True)),
                    host=FakeHost())
    assert not State(settings.state_file).is_published(date)
