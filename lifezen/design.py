"""Sistema di design: palette, font e primitive grafiche per le card lifezen.

1080x1080, estetica zen minimal: gradiente morbido, cornice sottile,
glow radiale, grana leggerissima, tipografia centrata (Lora + Inter).
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = 1080
FRAME_INSET = 46

FONT_FILES = {
    "serif": "Lora-Variable.ttf",
    "display": "CormorantGaramond-Variable.ttf",
    "sans": "Inter-Variable.ttf",
}

AXES = {
    "serif": {"Weight": (400, 700)},
    "display": {"Weight": (300, 700)},
    "sans": {"Weight": (100, 900), "Optical size": (14, 32)},
}


@dataclass(frozen=True)
class Palette:
    """Una palette completa per una card."""

    name: str
    bg_top: str
    bg_bottom: str
    glow: str
    ink: str
    muted: str
    accent: str
    frame: str

    def rgb(self, key: str) -> Tuple[int, int, int]:
        value = getattr(self, key)
        return hex_to_rgb(value)


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i: i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Palette: una famiglia per tipo di contenuto, con varianti che ruotano sul
# calendario in modo che il feed non risulti mai monocromo.
# ---------------------------------------------------------------------------

PALETTES: Dict[str, Palette] = {
    # --- pensiero: sabbia, carta, luce calda -----------------------------
    "sabbia": Palette("sabbia", "#F7F0E5", "#E7D6BE", "#FFF9EC", "#322A22", "#8E7F69", "#B9793F", "#D6BF9F"),
    "carta": Palette("carta", "#F5F2EB", "#DFD7C6", "#FFFDF4", "#2E2C27", "#857F70", "#8E7C4F", "#CFC6B0"),
    "ambra": Palette("ambra", "#F8F0DF", "#E8D4B4", "#FFFAEE", "#33291E", "#94806A", "#B0722F", "#D9C4A0"),
    # --- aforisma: salvia, eucalipto, pietra -----------------------------
    "salvia": Palette("salvia", "#EEF2EC", "#D3DFD0", "#F9FDF5", "#27342B", "#77877A", "#5C8163", "#C0CFBC"),
    "eucalipto": Palette("eucalipto", "#EAF1F0", "#CFDFDE", "#F7FCFB", "#253232", "#718284", "#4C7F7A", "#BCCFCC"),
    "nebbia": Palette("nebbia", "#EFF1F4", "#D5DCE3", "#FBFCFE", "#2A313A", "#7B868F", "#6C8098", "#C3CDD6"),
    # --- mantra: notte, indaco, luna -------------------------------------
    "notte": Palette("notte", "#1E2438", "#0A0E18", "#3D4A73", "#F4F1E9", "#98A2BE", "#CDB47A", "#39425F"),
    "indaco": Palette("indaco", "#1B2033", "#080A12", "#313D63", "#F2EEE5", "#929EBC", "#BCA66E", "#343C57"),
    "luna": Palette("luna", "#252B3C", "#0D1119", "#45527A", "#F6F3EC", "#A0A8C0", "#DBC78F", "#414A67"),
    # --- manifestazione: rosa cipria, oro, aurora ------------------------
    "aurora": Palette("aurora", "#FCF1EB", "#EFD6CB", "#FFF9F5", "#382927", "#96807C", "#BA6E52", "#DFBEAF"),
    "cipria": Palette("cipria", "#FAF0F0", "#E9D3D5", "#FFFAFA", "#362A2D", "#957E83", "#B87F87", "#DBBFC2"),
    "oro": Palette("oro", "#F9F2E3", "#E9D6B5", "#FFFBF1", "#332B1D", "#92815F", "#A87F32", "#D8C29A"),
    # --- consiglio: alba, acqua, menta -----------------------------------
    "alba": Palette("alba", "#FDF4E7", "#F3D9C0", "#FFFBF4", "#372C24", "#96836F", "#BC7B45", "#E2C6AA"),
    "acqua": Palette("acqua", "#EAF3F6", "#CFE2EA", "#F8FDFE", "#25323A", "#748A93", "#4E8394", "#BED5DE"),
    "menta": Palette("menta", "#EBF4EF", "#D2E5DA", "#F9FDFA", "#26332D", "#75877E", "#5C8B78", "#BFD5C8"),
}


TYPE_PALETTES: Dict[str, List[str]] = {
    "pensiero": ["sabbia", "carta", "ambra"],
    "aforisma": ["salvia", "eucalipto", "nebbia"],
    "mantra": ["notte", "indaco", "luna"],
    "manifestazione": ["aurora", "cipria", "oro"],
    "consiglio": ["alba", "acqua", "menta"],
}

TYPE_ORNAMENT = {
    "pensiero": "✦",
    "aforisma": "❋",
    "mantra": "☾",
    "manifestazione": "✧",
    "consiglio": "❖",
}


def palette_for(type_key: str, index: int = 0) -> Palette:
    names = TYPE_PALETTES.get(type_key) or ["sabbia"]
    return PALETTES[names[index % len(names)]]


# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=256)
def load_font(fonts_dir: Path, kind: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Carica un font variabile impostando il peso richiesto."""
    path = Path(fonts_dir) / FONT_FILES[kind]
    if not path.is_file():  # fallback di sistema
        for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            if Path(candidate).is_file():
                return ImageFont.truetype(candidate, size)
        raise FileNotFoundError(f"Font non trovato: {path}")
    font = ImageFont.truetype(str(path), size)
    axes = AXES.get(kind, {})
    if axes:
        try:
            # L'ordine degli assi è quello dichiarato dal font: per Inter è
            # [Optical size, Weight], quindi mappiamo per nome, non per posizione.
            values = []
            for axis in font.get_variation_axes():
                raw_name = axis["name"]
                axis_name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
                if axis_name in axes:
                    low, high = axes[axis_name]
                    values.append(int(max(low, min(high, weight))))
                else:
                    values.append(int(axis.get("default", 400)))
            if values:
                font.set_variation_by_axes(values)
        except Exception:  # pragma: no cover - font statico o FreeType datato
            pass
    return font


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def draw_spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill,
                spacing: float = 0.0, anchor_x: str = "c") -> float:
    """Disegna testo con spaziatura tra le lettere (letter-spacing manuale).

    xy è il punto di ancoraggio verticale centrale (anchor "lm"/"mm").
    Ritorna la larghezza totale disegnata.
    """
    if not spacing:
        anchor = "lm" if anchor_x == "l" else "mm" if anchor_x == "c" else "rm"
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return text_width(draw, text, font)

    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)
    if anchor_x == "c":
        x = xy[0] - total / 2
    elif anchor_x == "r":
        x = xy[0] - total
    else:
        x = xy[0]
    y = xy[1]
    for ch, width in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor="lm")
        x += width + spacing
    return total


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> List[str]:
    """Word-wrap rispettando gli accenti e le parole lunghe."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def text_block_height(draw: ImageDraw.ImageDraw, lines: Sequence[str], font, leading: float) -> float:
    if not lines:
        return 0.0
    sample = draw.textbbox((0, 0), "Àgjq", font=font)
    line_h = (sample[3] - sample[1]) * leading
    return line_h * len(lines)


def fit_text(draw: ImageDraw.ImageDraw, text: str, fonts_dir: Path, *,
             max_width: float, max_height: float, sizes: Sequence[int],
             weight: int = 450, leading: float = 1.34, kind: str = "serif"):
    """Trova dimensione e interruzioni di riga che meglio riempiono lo spazio."""
    best = None
    for size in sizes:
        font = load_font(Path(fonts_dir), kind, size, weight)
        lines = wrap_text(draw, text, font, max_width)
        height = text_block_height(draw, lines, font, leading)
        candidate = (size, font, lines, height)
        if height <= max_height:
            return candidate
        best = candidate
    return best  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Sfondi
# ---------------------------------------------------------------------------

def vertical_gradient(size: int, top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    strip = Image.new("RGB", (1, size))
    for y in range(size):
        strip.putpixel((0, y), mix(top, bottom, y / max(1, size - 1)))
    return strip.resize((size, size), Image.Resampling.BILINEAR)


def radial_mask(size: int, *, center: Tuple[float, float] = (0.5, 0.42), radius: float = 0.72,
                invert: bool = False) -> Image.Image:
    """Maschera radiale morbida (bianco al centro) costruita a bassa risoluzione."""
    res = 256
    mask = Image.new("L", (res, res))
    pixels = mask.load()
    cx, cy = center[0] * res, center[1] * res
    max_distance = radius * res
    for y in range(res):
        for x in range(res):
            distance = math.hypot(x - cx, y - cy) / max_distance
            value = 255 * max(0.0, min(1.0, 1.0 - distance)) ** 1.6
            pixels[x, y] = int(value)
    mask = mask.resize((size, size), Image.Resampling.BICUBIC)
    return ImageOps.invert(mask) if invert else mask


def paper_grain(size: int, amount: float = 0.05) -> Image.Image:
    noise = Image.effect_noise((size, size), 22).convert("RGB")
    return Image.blend(Image.new("RGB", (size, size), (128, 128, 128)), noise, amount)


def build_background(size: int, palette: Palette) -> Image.Image:
    """Gradiente + glow + vignettatura + grana."""
    base = vertical_gradient(size, palette.rgb("bg_top"), palette.rgb("bg_bottom"))
    canvas = base.convert("RGB")

    # alone luminoso: dà profondità senza slavare il fondo
    glow_mask = radial_mask(size, center=(0.5, 0.34), radius=0.62).point(lambda v: int(v * 0.40))
    glow_layer = Image.new("RGB", (size, size), palette.rgb("glow"))
    canvas = Image.composite(glow_layer, canvas, glow_mask)

    # vignettatura: raccoglie lo sguardo verso il centro
    vignette = radial_mask(size, center=(0.5, 0.48), radius=0.98, invert=True).point(lambda v: int(v * 0.52))
    shade = mix(palette.rgb("bg_bottom"), (10, 10, 14), 0.55)
    canvas = Image.composite(Image.new("RGB", (size, size), shade), canvas, vignette)

    # grana leggerissima da carta pregiata
    canvas = Image.blend(canvas, paper_grain(size), 0.030)
    return canvas


# ---------------------------------------------------------------------------
# Elementi decorativi
# ---------------------------------------------------------------------------

def draw_frame(draw: ImageDraw.ImageDraw, size: int, palette: Palette, inset: int = FRAME_INSET) -> None:
    color = palette.rgb("frame")
    draw.rectangle([inset, inset, size - inset - 1, size - inset - 1], outline=color, width=2)
    inner = inset + 12
    soft = mix(color, palette.rgb("bg_top"), 0.55)
    draw.rectangle([inner, inner, size - inner - 1, size - inner - 1], outline=soft, width=1)


def draw_corners(draw: ImageDraw.ImageDraw, size: int, palette: Palette, inset: int = FRAME_INSET) -> None:
    """Piccoli angoli a 'L' più marcati: dettaglio artigianale."""
    color = palette.rgb("accent")
    length = 34
    offset = inset + 22
    for (x, y, dx, dy) in (
        (offset, offset, 1, 1),
        (size - offset, offset, -1, 1),
        (offset, size - offset, 1, -1),
        (size - offset, size - offset, -1, -1),
    ):
        draw.line([(x, y), (x + dx * length, y)], fill=color, width=3)
        draw.line([(x, y), (x, y + dy * length)], fill=color, width=3)


def draw_separator(draw: ImageDraw.ImageDraw, cx: float, cy: float, palette: Palette, *,
                   width: float = 150.0, ornament: str = "◆", fonts_dir: Path = None) -> None:
    color = palette.rgb("accent")
    gap = 26 if ornament else 0
    draw.line([(cx - width / 2, cy), (cx - gap, cy)], fill=color, width=2)
    draw.line([(cx + gap, cy), (cx + width / 2, cy)], fill=color, width=2)
    if ornament and fonts_dir:
        font = load_font(Path(fonts_dir), "sans", 20, 500)
        draw.text((cx, cy), ornament, font=font, fill=color, anchor="mm")
    elif ornament:
        r = 5
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=color)


def draw_flanked_label(draw: ImageDraw.ImageDraw, cx: float, cy: float, text: str, palette: Palette,
                       fonts_dir: Path, *, size: int = 27, weight: int = 550,
                       spacing: float = 4.6, line_width: float = 74.0) -> None:
    font = load_font(Path(fonts_dir), "sans", size, weight)
    width = draw_spaced(draw, (cx, cy), text.upper(), font, palette.rgb("accent"), spacing)
    half = width / 2
    color = palette.rgb("frame")
    draw.line([(cx - half - line_width, cy), (cx - half - 20, cy)], fill=color, width=2)
    draw.line([(cx + half + 20, cy), (cx + half + line_width, cy)], fill=color, width=2)
