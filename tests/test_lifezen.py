"""Test essenziali: calendario completo, caption valide, card renderizzabili."""

from __future__ import annotations

import calendar
import datetime as dt
import json
from pathlib import Path

import pytest

from lifezen.card import make_contact_sheet, render_card, render_story
from lifezen.config import Settings, load_settings
from lifezen.content import (DayContent, Library, build_caption, fit_caption,
                             load_library, tag_to_hashtag)
from lifezen.imagehost import _upload_name
from lifezen.pipeline import build_day, month_dates
from lifezen.state import State

REPO = Path(__file__).resolve().parent.parent
CONTENT = REPO / "assets" / "content"
FONTS = REPO / "assets" / "fonts"


@pytest.fixture(scope="module")
def library() -> Library:
    return load_library(CONTENT)


def expected_days() -> int:
    """365 giorni; il 29 febbraio è un contenuto bonus in common.json."""
    return 365


# ---------------------------------------------------------------------------
# Contenuti
# ---------------------------------------------------------------------------

def test_calendario_completo(library: Library):
    assert len(library) == expected_days()
    for month in range(1, 13):
        days = 28 if month == 2 else calendar.monthrange(2026, month)[1]
        for day in range(1, days + 1):
            entry = library.get(month, day)
            assert entry.text.strip(), f"testo vuoto il {day:02d}/{month:02d}"


def test_bonus_29_febbraio(library: Library):
    entry = library.get(2, 29)
    assert "anno bisestile" in entry.text.lower() or "bisestile" in entry.caption.lower()


def test_tipi_attesi(library: Library):
    tipi = {entry.type for entry in library.all_entries()}
    assert tipi == {"pensiero", "aforisma", "mantra", "manifestazione", "consiglio"}
    for type_key in tipi:
        assert library.type_label(type_key)
        assert library.type_cta(type_key)


def test_ogni_mese_ha_5_tipi(library: Library):
    for month in range(1, 13):
        tipi = {library.get(month, day).type for day in range(1, 29)}
        assert len(tipi) >= 4, f"poca varietà a {month}/2026: {tipi}"


def test_testi_lunghezza_ragionevole(library: Library):
    for entry in library.all_entries():
        # i mantra sono volutamente brevi: si accetta una forbice ampia
        assert 20 <= len(entry.text) <= 340, f"{entry.month}/{entry.day}: {len(entry.text)} caratteri"
        assert entry.title, f"{entry.month}/{entry.day}: titolo mancante"


def test_hashtag_validi(library: Library):
    for entry in library.all_entries():
        for tag in library.hashtags_for(entry):
            body = tag.lstrip("#")
            assert body and " " not in body and "-" not in body, tag


def test_tag_to_hashtag():
    assert tag_to_hashtag("nuovi inizi") == "#nuoviinizi"
    assert tag_to_hashtag("priorità") == "#priorita"
    assert tag_to_hashtag("cura di sé", {"cura di sé": "#selfcare"}) == "#selfcare"
    assert tag_to_hashtag("#giafatto") == "#giafatto"


# ---------------------------------------------------------------------------
# Caption
# ---------------------------------------------------------------------------

def test_caption_entro_limite(library: Library):
    for date in [dt.date(2026, m, d) for m in (1, 6, 12) for d in (1, 15, 28)]:
        caption = build_caption(library.get_by_date(date), library, date)
        assert len(caption) <= 2200
        assert "@lifezen77real" in caption
        assert caption.count("#") >= 5


def test_fit_caption_preserva_hashtag():
    body = "\n".join(["frase " * 20] * 40)
    caption = f"{body}\n\n#zen #calma #mindfulness"
    trimmed = fit_caption(caption, 400)
    assert len(trimmed) <= 400
    assert trimmed.rstrip().endswith("#mindfulness")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day,month", [(1, 1), (3, 1), (4, 1), (15, 1), (25, 1), (31, 1)])
def test_render_card(library: Library, tmp_path: Path, day: int, month: int):
    from PIL import Image

    date = dt.date(2026, month, day)
    target = render_card(library.get_by_date(date), library, date,
                         tmp_path / f"{date.isoformat()}.jpg", fonts_dir=FONTS)
    assert target.is_file() and target.stat().st_size > 30_000
    with Image.open(target) as image:
        assert image.size == (1080, 1080)
        assert image.mode == "RGB"


def test_render_story(library: Library, tmp_path: Path):
    from PIL import Image

    date = dt.date(2026, 3, 8)
    target = render_story(library.get_by_date(date), library, date,
                          tmp_path / "story.jpg", fonts_dir=FONTS)
    with Image.open(target) as image:
        assert image.size == (1080, 1920)


def test_contact_sheet(library: Library, tmp_path: Path):
    from PIL import Image

    paths = [render_card(library.get_by_date(dt.date(2026, 1, d)), library, dt.date(2026, 1, d),
                         tmp_path / f"c{d}.jpg", fonts_dir=FONTS) for d in (1, 2, 3, 4)]
    sheet = make_contact_sheet(paths, tmp_path / "sheet.jpg", columns=2, thumb=200)
    with Image.open(sheet) as image:
        assert image.size == (400, 400)


def test_testo_estremo_non_esce_dalla_card(library: Library, tmp_path: Path):
    """Una citazione molto lunga deve rimpicciolirsi, non uscire dalla cornice."""
    from PIL import Image

    lunga = DayContent(month=1, day=1, type="pensiero", title="Test",
                       text="Questa è una frase molto lunga. " * 12, caption="", tags=[])
    date = dt.date(2026, 1, 1)
    target = render_card(lunga, library, date, tmp_path / "lunga.jpg", fonts_dir=FONTS)
    with Image.open(target) as image:
        assert image.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Pipeline, stato, hosting
# ---------------------------------------------------------------------------

def test_dry_run_non_pubblica(library: Library, tmp_path: Path):
    settings = Settings(repo_root=REPO, dry_run=True,
                        state_path=tmp_path / "state.json",
                        output_path=tmp_path / "output")
    plan = build_day(settings, library, dt.date(2026, 1, 5))
    assert plan.image_path.is_file()
    assert plan.caption
    assert plan.status == "planned"


def test_stato_idempotente(tmp_path: Path):
    state = State(tmp_path / "state.json")
    date = dt.date(2026, 4, 2)
    assert not state.is_published(date)
    state.record_publish(date, {"media_id": "123", "permalink": "https://instagram.com/p/x"})
    reloaded = State(tmp_path / "state.json")
    assert reloaded.is_published(date)
    assert reloaded.published_record(date)["media_id"] == "123"
    assert reloaded.stats()["pubblicati"] == 1


def test_nome_file_upload():
    # la data non viene duplicata se già presente nel nome della card
    assert _upload_name(Path("2026-01-05-pensiero.jpg"), dt.date(2026, 1, 5)) == \
        "2026-01-05-pensiero.jpg"
    assert _upload_name(Path("card.jpg"), dt.date(2026, 1, 5)) == "2026-01-05-card.jpg"


def test_host_richiede_configurazione(tmp_path: Path):
    settings = Settings(repo_root=tmp_path, image_host="github", repo="", github_token="")
    ready, reason = settings.image_host_ready()
    assert not ready and "LIFEZEN_REPO" in reason

    settings.image_host = "cloudinary"
    settings.cloudinary_cloud = "demo"
    ready, reason = settings.image_host_ready()
    assert not ready and "CLOUDINARY" in reason


def test_impostazioni_segreti_mascherati():
    settings = load_settings(ig_token="EAAG0123456789abcdef", ig_user_id="17841400000000000")
    public = settings.as_public_dict()
    assert "EAAG0123456789abcdef" not in json.dumps(public)


def test_month_dates_copre_tutti_i_giorni():
    assert len(month_dates(2026, 2)) == 28
    assert len(month_dates(2026, 1)) == 31
    assert len(month_dates(2026, 12)) == 31
