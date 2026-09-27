"""Pagina HTML locale per rivedere tutte le card dell'anno in una griglia."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List, Sequence

from .content import Library

TYPE_CLASS = {
    "pensiero": "t-pensiero",
    "aforisma": "t-aforisma",
    "mantra": "t-mantra",
    "manifestazione": "t-manifestazione",
    "consiglio": "t-consiglio",
}

STYLE = """
  :root {
    --bg: #14161c; --panel: #1b1e26; --ink: #efece4; --muted: #8f8f9b;
    --accent: #cdb47a; --line: #2a2e39;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif; }
  header.top { padding: 48px 24px 24px; text-align: center; border-bottom: 1px solid var(--line); }
  header.top h1 { margin: 0 0 6px; font-family: Georgia, "Lora", serif; font-weight: 500;
                  font-size: clamp(28px, 4vw, 44px); letter-spacing: .01em; }
  header.top p { margin: 0; color: var(--muted); }
  nav { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 6px;
        justify-content: center; padding: 12px; background: rgba(20,22,28,.92);
        backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
  nav a { color: var(--muted); text-decoration: none; font-size: 12px; letter-spacing: .12em;
          padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px; }
  nav a:hover { color: var(--ink); border-color: var(--accent); }
  main { max-width: 1500px; margin: 0 auto; padding: 32px 24px 80px; }
  .month { margin-bottom: 56px; }
  .month header { display: flex; align-items: baseline; justify-content: space-between;
                  gap: 16px; border-bottom: 1px solid var(--line); padding-bottom: 12px;
                  margin-bottom: 20px; }
  .month h2 { margin: 0; font-family: Georgia, "Lora", serif; font-weight: 500;
              font-size: clamp(20px, 2.5vw, 30px); }
  .month h2 span { color: var(--accent); font-size: .7em; }
  .month p { margin: 0; color: var(--muted); font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 18px; }
  .card { margin: 0; background: var(--panel); border: 1px solid var(--line);
          border-radius: 12px; overflow: hidden; }
  .card img { width: 100%; display: block; aspect-ratio: 1/1; object-fit: cover; }
  .card figcaption { padding: 12px 14px 14px; display: grid; gap: 4px; }
  .card .day { color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
  .card strong { font-weight: 500; font-size: 14px; }
  .type { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); }
  .t-mantra { color: #9db2e0; }
  .t-manifestazione { color: #d29bb0; }
  .t-consiglio { color: #93c1a3; }
  .t-aforisma { color: #b8c79c; }
  footer { text-align: center; color: var(--muted); font-size: 13px; padding: 24px; }
"""


def render_gallery_html(plans: Sequence, library: Library, year: int,
                        cards_dir_name: str = "cards") -> str:
    """Costruisce l'HTML completo (nessuna risorsa esterna)."""
    months_html: List[str] = []
    for month in range(1, 13):
        month_plans = [plan for plan in plans if plan.date.month == month]
        if not month_plans:
            continue
        cards = []
        for plan in month_plans:
            entry = plan.entry
            rel = f"../{cards_dir_name}/{plan.image_path.name}"
            cards.append(f"""
          <figure class="card">
            <img src="{escape(rel)}" alt="{escape(entry.title)}" loading="lazy">
            <figcaption>
              <span class="day">{plan.date.day:02d}/{month:02d} · giorno {plan.day_number}</span>
              <strong>{escape(entry.title)}</strong>
              <span class="type {TYPE_CLASS.get(entry.type, '')}">{escape(library.type_label(entry.type))}</span>
            </figcaption>
          </figure>""")
        months_html.append(f"""
      <section class="month" id="mese-{month}">
        <header>
          <h2>{escape(library.month_name(month))} <span>· {escape(library.month_theme(month))}</span></h2>
          <p>{len(month_plans)} contenuti</p>
        </header>
        <div class="grid">{''.join(cards)}</div>
      </section>""")

    nav = "".join(
        f'<a href="#mese-{month}">{escape(library.month_name(month)[:3].upper())}</a>'
        for month in range(1, 13)
        if any(plan.date.month == month for plan in plans)
    )
    handle = escape(library.brand.get("handle", "@lifezen77real"))
    total = len(plans)

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>myLifeZen {year} — calendario dei contenuti</title>
<style>{STYLE}</style>
</head>
<body>
  <header class="top">
    <h1>myLifeZen — calendario {year}</h1>
    <p>{total} pensieri, aforismi, mantra e manifestazioni per {handle}</p>
  </header>
  <nav>{nav}</nav>
  <main>{''.join(months_html)}</main>
  <footer>Generato con <code>python -m lifezen gallery</code> · myLifeZen</footer>
</body>
</html>
"""


def write_gallery(plans: Sequence, library: Library, year: int, target: Path,
                  cards_dir_name: str = "cards") -> Path:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_gallery_html(plans, library, year, cards_dir_name),
                      encoding="utf-8")
    return target
