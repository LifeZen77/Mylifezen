"""Rendering delle card 1080x1080 per il feed Instagram."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List, Optional, Sequence

from PIL import Image, ImageDraw

from .content import DayContent, Library, day_of_year
from .design import (SIZE, build_background, draw_corners, draw_flanked_label,
                     draw_frame, draw_separator, draw_spaced, load_font, palette_for,
                     text_block_height, wrap_text)

MAX_TEXT_WIDTH = 812
MAX_TEXT_HEIGHT = 466
CENTER_Y = 492          # centro ottico del blocco citazione
SEPARATOR_MAX_Y = 772   # il separatore non scende mai oltre
COUNTER_Y = 906
HANDLE_Y = 956
QUOTE_SIZES: Sequence[int] = tuple(range(72, 34, -2))
LABEL_ORNAMENTS = {"pensiero": "✦", "aforisma": "❋", "mantra": "☾",
                   "manifestazione": "✧", "consiglio": "❖"}


def _wrap_paragraphs(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> List[str]:
    lines: List[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        lines.extend(wrap_text(draw, paragraph, font, max_width))
    return lines or [""]


def _fit_quote(draw: ImageDraw.ImageDraw, text: str, fonts_dir: Path):
    """Sceglie la dimensione più grande che entra nell'area della citazione."""
    best = None
    for size in QUOTE_SIZES:
        font = load_font(Path(fonts_dir), "serif", size, 470)
        lines = _wrap_paragraphs(draw, text, font, MAX_TEXT_WIDTH)
        height = text_block_height(draw, lines, font, 1.34)
        best = (font, lines, height, size)
        if height <= MAX_TEXT_HEIGHT:
            return best
    return best


def _quote_text(entry: DayContent) -> str:
    text = entry.text.strip()
    if entry.type == "aforisma" and not text.startswith(("«", "“", '"')):
        return f"«{text}»"
    return text


def render_card(entry: DayContent, library: Library, date: dt.date, output_path: Path,
                *, fonts_dir: Optional[Path] = None, palette_index: Optional[int] = None,
                show_day_counter: bool = True) -> Path:
    """Genera la card e la salva come JPEG (formato richiesto da Instagram)."""
    fonts_dir = Path(fonts_dir) if fonts_dir else Path(__file__).resolve().parent.parent / "assets" / "fonts"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if palette_index is None:
        palette_index = (day_of_year(date) + entry.day) % 7
    palette = palette_for(entry.type, palette_index)

    image = build_background(SIZE, palette)
    draw = ImageDraw.Draw(image)
    draw_frame(draw, SIZE, palette)
    draw_corners(draw, SIZE, palette)

    # --- etichetta di tipo, in alto ------------------------------------
    label = library.type_label(entry.type)
    ornament = LABEL_ORNAMENTS.get(entry.type, "✦")
    draw_flanked_label(draw, SIZE / 2, 176, f"{ornament}  {label}  {ornament}", palette, fonts_dir)

    # --- citazione, centrata ------------------------------------------
    quote = _quote_text(entry)
    font, lines, height, size = _fit_quote(draw, quote, fonts_dir)
    line_h = height / max(1, len(lines))
    block_top = CENTER_Y - height / 2
    color = palette.rgb("ink")
    for index, line in enumerate(lines):
        draw.text((SIZE / 2, block_top + line_h * index + line_h / 2), line,
                  font=font, fill=color, anchor="mm")

    # --- separatore: sotto la citazione, mai addosso alla firma ---------
    separator_y = min(SEPARATOR_MAX_Y, block_top + height + 58)
    draw_separator(draw, SIZE / 2, separator_y, palette, width=170,
                   ornament=ornament, fonts_dir=fonts_dir)

    # --- firma ---------------------------------------------------------
    brand = library.brand
    handle = brand.get("handle", "@lifezen77real")
    if show_day_counter:
        counter_font = load_font(Path(fonts_dir), "sans", 21, 550)
        draw_spaced(draw, (SIZE / 2, COUNTER_Y),
                    f"GIORNO {day_of_year(date)} / 365", counter_font,
                    palette.rgb("muted"), spacing=6.0)

    handle_font = load_font(Path(fonts_dir), "sans", 33, 620)
    draw_spaced(draw, (SIZE / 2, HANDLE_Y), handle, handle_font, palette.rgb("ink"), spacing=2.4)

    suffix = output_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        image.convert("RGB").save(output_path, "JPEG", quality=94, optimize=True,
                                  progressive=True, subsampling=0)
    else:
        image.save(output_path)

    return output_path


def render_story(entry: DayContent, library: Library, date: dt.date, output_path: Path,
                 *, fonts_dir: Optional[Path] = None) -> Path:
    """Variante 1080x1920 per le storie (utile per il cross-posting manuale)."""
    fonts_dir = Path(fonts_dir) if fonts_dir else Path(__file__).resolve().parent.parent / "assets" / "fonts"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    palette = palette_for(entry.type, (day_of_year(date) + entry.day) % 7)
    base = build_background(SIZE, palette).resize((SIZE, 1920), Image.Resampling.BICUBIC)
    image = base.convert("RGB")
    draw = ImageDraw.Draw(image)

    inset = 60
    draw.rectangle([inset, inset, SIZE - inset - 1, 1920 - inset - 1],
                   outline=palette.rgb("frame"), width=2)

    label = library.type_label(entry.type)
    draw_flanked_label(draw, SIZE / 2, 330, label, palette, fonts_dir)

    quote = _quote_text(entry)
    font, lines, height, _ = _fit_quote(draw, quote, fonts_dir)
    line_h = height / max(1, len(lines))
    block_top = 960 - height / 2
    for index, line in enumerate(lines):
        draw.text((SIZE / 2, block_top + line_h * index + line_h / 2), line,
                  font=font, fill=palette.rgb("ink"), anchor="mm")

    ornament = LABEL_ORNAMENTS.get(entry.type, "✦")
    draw_separator(draw, SIZE / 2, block_top + height + 80, palette, width=180,
                   ornament=ornament, fonts_dir=fonts_dir)

    draw_spaced(draw, (SIZE / 2, 1620), f"GIORNO {day_of_year(date)} / 365",
                load_font(Path(fonts_dir), "sans", 26, 550), palette.rgb("muted"), spacing=7.0)
    draw_spaced(draw, (SIZE / 2, 1680), library.brand.get("handle", "@lifezen77real"),
                load_font(Path(fonts_dir), "sans", 40, 620), palette.rgb("ink"), spacing=2.6)

    story_hint = library.brand.get("story_cta", "Salva questo pensiero ✦")
    draw_spaced(draw, (SIZE / 2, 1760), story_hint,
                load_font(Path(fonts_dir), "sans", 28, 500), palette.rgb("accent"), spacing=1.2)

    image.save(output_path, "JPEG", quality=93, optimize=True, progressive=True, subsampling=0)
    return output_path


def make_contact_sheet(paths: Sequence[Path], output_path: Path, columns: int = 3,
                       thumb: int = 360) -> Path:
    """Griglia di anteprima per controllare a colpo d'occhio un mese intero."""
    paths = list(paths)
    if not paths:
        raise ValueError("Nessuna immagine da impaginare")
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb, rows * thumb), (24, 24, 28))
    for index, path in enumerate(paths):
        with Image.open(path) as handle:
            image = handle.convert("RGB").resize((thumb, thumb), Image.Resampling.LANCZOS)
        sheet.paste(image, ((index % columns) * thumb, (index // columns) * thumb))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "JPEG", quality=88, optimize=True)
    return output_path
