"""Interfaccia a riga di comando di myLifeZen.

Esempi:
    python -m lifezen run                     # pubblica il contenuto di oggi
    python -m lifezen run --dry-run           # prepara tutto senza pubblicare
    python -m lifezen run --date 2026-03-01   # pubblica una data specifica
    python -m lifezen preview --month 3       # genera le card di un mese
    python -m lifezen doctor                  # diagnosi completa
    python -m lifezen auth pages              # trova IG_USER_ID
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import logging
import sys

from .card import make_contact_sheet
from .config import load_settings
from .content import build_caption, load_library
from .imagehost import ImageHost
from .instagram import InstagramClient, InstagramError
from .pipeline import build_day, month_dates, run_for_date, summary, today_in
from .state import State

LOG = logging.getLogger("lifezen")
LOG_FORMAT = "%(asctime)s  %(levelname)-7s %(message)s"
DATE_FORMAT = "%H:%M:%S"

TYPE_ICONS = {"pensiero": "✦", "aforisma": "❋", "mantra": "☾",
              "manifestazione": "✧", "consiglio": "❖"}


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format=LOG_FORMAT, datefmt=DATE_FORMAT, stream=sys.stdout)


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Data non valida: {value!r} (formato AAAA-MM-GG)")


def _load(args) -> tuple:
    settings = load_settings()
    if getattr(args, "dry_run", False):
        settings.dry_run = True
    library = load_library(settings.content_dir)
    return settings, library


# ---------------------------------------------------------------------------
# Comandi
# ---------------------------------------------------------------------------

def cmd_run(args) -> int:
    settings, library = _load(args)
    date = args.date or today_in(settings)
    LOG.info("myLifeZen — %s | host immagini: %s | dry-run: %s",
             date.isoformat(), settings.image_host, settings.dry_run)
    plan = run_for_date(settings, library, date, force=args.force,
                        with_story=args.story, dry_run=args.dry_run)
    print()
    print(f"  {TYPE_ICONS.get(plan.entry.type, '•')}  {plan.entry.title}")
    print(f"  {plan.entry.text.splitlines()[0]}")
    print(f"  tipo: {plan.entry.type}  ·  giorno {plan.day_number}/365")
    print(f"  card: {plan.image_path}")
    if plan.story_path:
        print(f"  story: {plan.story_path}")
    if plan.permalink:
        print(f"  post: {plan.permalink}")
    print(f"  stato: {plan.status} {plan.message}")
    print()
    print(f"  caption ({len(plan.caption)} caratteri):")
    for line in plan.caption.splitlines():
        print(f"    {line}")
    print()
    return 0 if plan.status in {"pubblicato", "dry-run", "saltato (già pubblicato)"} else 1


def cmd_preview(args) -> int:
    settings, library = _load(args)
    if args.month:
        year = args.year or today_in(settings).year
        dates = month_dates(year, args.month)
    else:
        today = args.date or today_in(settings)
        dates = [today + dt.timedelta(days=offset) for offset in range(args.next)]

    plans = []
    for date in dates:
        plan = build_day(settings, library, date, with_story=args.story)
        plans.append(plan)
        print(f"  {date.isoformat()}  {TYPE_ICONS.get(plan.entry.type, '•')} {plan.entry.type:<15} "
              f"{plan.entry.title or '—'}  ->  {plan.image_path.name}")

    if args.sheet and len(plans) > 1:
        target = settings.output_dir / "sheets" / (
            f"{plans[0].date.isoformat()}_{plans[-1].date.isoformat()}.jpg")
        make_contact_sheet([p.image_path for p in plans], target,
                           columns=args.columns, thumb=args.thumb)
        print(f"\n  Anteprima griglia: {target}")
    return 0


def cmd_publish_month(args) -> int:
    settings, library = _load(args)
    year = args.year or today_in(settings).year
    dates = month_dates(year, args.month)
    today = today_in(settings)
    dates = [d for d in dates if d <= today]
    if args.all_days:
        dates = month_dates(year, args.month)

    LOG.info("Pubblicazione arretrata: %s giorni di %s/%s (dry-run: %s)",
             len(dates), args.month, year, settings.dry_run)
    results = []
    for date in dates:
        try:
            plan = run_for_date(settings, library, date, force=args.force, dry_run=settings.dry_run)
        except Exception as exc:
            LOG.error("%s: %s", date.isoformat(), exc)
            continue
        results.append(plan)
        if not settings.dry_run and args.sleep:
            import time
            time.sleep(args.sleep)
    print()
    for status, count in summary(results).items():
        print(f"  {status}: {count}")
    return 0


def cmd_doctor(args) -> int:
    settings = load_settings()
    library = load_library(settings.content_dir)
    ok = True

    print("\n  myLifeZen · diagnosi\n" + "  " + "─" * 46)
    print(f"  giorni in libreria        : {len(library)}/365 (+ 29/02 negli anni bisestili)")
    missing = [f"{d:02d}/{m:02d}" for m in range(1, 13)
               for d in _valid_days(m) if not _exists(library, m, d)]
    if missing:
        ok = False
        print(f"  giorni mancanti           : {', '.join(missing[:12])}"
              f"{' …' if len(missing) > 12 else ''}  ({len(missing)} totali)")
    else:
        print("  calendario                : completo ✓")

    print(f"  fusi orari                : {settings.timezone}")
    print(f"  host immagini             : {settings.image_host} ({settings.cdn})")
    ready, reason = settings.image_host_ready()
    if not ready:
        ok = False
        print(f"  host immagini             : ✗ {reason}")
    else:
        print("  host immagini             : configurato ✓")

    missing_pub = settings.missing_for_publish()
    if missing_pub:
        ok = False
        print(f"  credenziali Instagram     : ✗ mancano {', '.join(missing_pub)}")
        print("\n  Configura il .env seguendo README.md (sezione «Collegare Instagram»).")
        return 1

    print("  credenziali Instagram     : presenti ✓")
    if args.offline:
        return 0 if ok else 1

    client = InstagramClient(settings)
    host = ImageHost(settings)
    try:
        for key, value in client.health_check().items():
            print(f"  {key:<25}: {value}")
    except InstagramError as exc:
        ok = False
        print(f"  Instagram                 : ✗ {exc}")
        if "getattr" in str(exc):  # pragma: no cover
            pass

    # prova end-to-end dell'hosting immagini
    try:
        from .pipeline import build_day
        date = args.date or today_in(settings)
        plan = build_day(settings, library, date)
        uploaded = host.upload(plan.image_path, date)
        reachable = host.check_remote(uploaded.url)
        print(f"  upload di prova          : {uploaded.backend} · {uploaded.url}")
        print(f"  immagine raggiungibile   : {'sì ✓' if reachable else 'NO ✗'}")
        if not reachable and uploaded.alt_url:
            print(f"  URL alternativo valido   : {'sì' if host.check_remote(uploaded.alt_url) else 'no'}")
        ok = ok and reachable
    except Exception as exc:
        ok = False
        print(f"  upload di prova          : ✗ {exc}")

    print(f"\n  STATO: {'pronto a pubblicare ✓' if ok else 'da sistemare ✗'}\n")
    return 0 if ok else 1


def cmd_gallery(args) -> int:
    """Genera una pagina HTML locale con tutte le card dell'anno."""
    from .gallery import write_gallery

    settings, library = _load(args)
    year = args.year or today_in(settings).year
    dates = [date for month in range(1, 13) for date in month_dates(year, month)]
    plans = [build_day(settings, library, date) for date in dates]

    target = write_gallery(plans, library, year, settings.output_dir / "gallery" /
                           f"calendario-{year}.html")
    print(f"\n  {len(plans)} card generate per il calendario {year}")
    print(f"  Anteprima nel browser: file://{target}\n")
    return 0


def _valid_days(month: int, year: int = 2024) -> range:
    """Giorni reali del mese; per febbraio si usa un anno bisestile (28 + bonus 29/02)."""
    days = calendar.monthrange(year, month)[1]
    if month == 2:
        days = 28  # il 29/02 è gestito come contenuto bonus in common.json
    return range(1, days + 1)


def _exists(library, month: int, day: int) -> bool:
    try:
        library.get(month, day)
        return True
    except Exception:
        return False


def cmd_auth(args) -> int:
    settings = load_settings()
    import requests

    if args.action == "exchange":
        if not (settings.app_id and settings.app_secret):
            print("  Servono IG_APP_ID e IG_APP_SECRET nel .env")
            return 1
        response = requests.get(f"{settings.graph_base}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.app_id,
            "client_secret": settings.app_secret,
            "fb_exchange_token": args.token,
        }, timeout=30)
        data = response.json()
        if "access_token" not in data:
            print(f"  Errore: {json.dumps(data)}")
            return 1
        print("\n  Token a lunga durata (60 giorni). Aggiungilo al .env:\n")
        print(f"  IG_ACCESS_TOKEN={data['access_token']}\n")
        return 0

    if args.action == "pages":
        if not args.token:
            print("  Serve --token <token utente Facebook>. Ottienilo dal Graph API Explorer\n"
                  "  con i permessi pages_show_list, instagram_basic, instagram_content_publish,\n"
                  "  pages_read_engagement, business_management.")
            return 1
        response = requests.get(f"{settings.graph_base}/me/accounts", params={
            "access_token": args.token,
            "fields": "name,id,access_token,instagram_business_account{id,username,followers_count}",
        }, timeout=30)
        data = response.json()
        if "data" not in data:
            print(f"  Errore: {json.dumps(data)}")
            return 1
        print("\n  Pagine Facebook collegate:\n")
        for page in data["data"]:
            account = page.get("instagram_business_account") or {}
            print(f"  • Pagina: {page['name']}  (id {page['id']})")
            if account:
                print(f"    ↳ Instagram: @{account.get('username', '?')} "
                      f"— IG_USER_ID={account['id']} "
                      f"({account.get('followers_count', '?')} follower)")
                print(f"    IG_ACCESS_TOKEN={page.get('access_token', '<manca>')}")
            else:
                print("    ↳ nessun account Instagram Business collegato a questa Pagina")
            print()
        print("  Copia i valori nel file .env e lancia: python -m lifezen doctor\n")
        return 0

    if args.action == "check":
        settings_ok = settings.missing_for_publish()
        if settings_ok:
            print(f"  Manca: {', '.join(settings_ok)}")
            return 1
        client = InstagramClient(settings)
        for key, value in client.health_check().items():
            print(f"  {key:<25}: {value}")
        return 0

    print(f"  Azione sconosciuta: {args.action}")
    return 1


def cmd_check(args) -> int:
    """Verifica strutturale della libreria e della caption di oggi."""
    settings, library = _load(args)
    problems = []
    seen_types = {}
    for month in range(1, 13):
        for day in _valid_days(month):
            try:
                entry = library.get(month, day)
            except Exception:
                problems.append(f"manca {day:02d}/{month:02d}")
                continue
            seen_types[entry.type] = seen_types.get(entry.type, 0) + 1
            if not entry.text.strip():
                problems.append(f"{day:02d}/{month:02d}: testo vuoto")
            if len(entry.text) > 420:
                problems.append(f"{day:02d}/{month:02d}: testo lungo ({len(entry.text)} caratteri)")

    print(f"\n  giorni: {len(library)}")
    print("  tipi:", ", ".join(f"{k}={v}" for k, v in sorted(seen_types.items())))
    if problems:
        print(f"\n  {len(problems)} problemi:")
        for problem in problems[:40]:
            print(f"    - {problem}")
        return 1

    date = args.date or today_in(settings)
    entry = library.get_by_date(date)
    caption = build_caption(entry, library, date, cta_site=settings.cta_site)
    print(f"\n  caption di {date.isoformat()}: {len(caption)} caratteri (limite {settings.caption_limit})")
    print("  libreria valida ✓\n")
    return 0


def cmd_stats(args) -> int:
    settings = load_settings()
    state = State(settings.state_file)
    stats = state.stats()
    print("\n  myLifeZen · cronologia\n" + "  " + "─" * 46)
    for key, value in stats.items():
        print(f"  {key:<12}: {value}")
    record = state.published_record(today_in(settings))
    print(f"  oggi         : {'pubblicato' if record else 'non ancora pubblicato'}")
    runs = state.data.get("runs", [])[:5]
    if runs:
        print("\n  ultime esecuzioni:")
        for run in runs:
            print(f"    {run.get('at', '?')}  {run.get('date', '')}  {run.get('status', '')}"
                  f"  {run.get('message', '')}")
    print()
    return 0


def cmd_cron(args) -> int:
    """Stampa lo schedule consigliato (cron locale o GitHub Actions)."""
    tz = args.timezone or "Europe/Rome"
    print(f"""
  myLifeZen · pianificazione

  ▶ GitHub Actions (consigliato, nessun computer acceso)
    Il workflow .github/workflows/daily-post.yml gira ogni giorno alle 06:10 UTC
    (08:10 circa in Italia in estate, 07:10 in inverno).
    Puoi cambiare l'orario dal file o dalla scheda Actions di GitHub.

  ▶ Cron locale (fuso {tz})
    Per pubblicare ogni giorno alle 8:00 ora italiana, aggiungi con `crontab -e`:

    0 8 * * *  cd {args.path or '/percorso/del/repo'} && /usr/bin/python3 -m lifezen run >> logs/lifezen.log 2>&1

  ▶ Verifica
    python -m lifezen doctor        # tutto pronto?
    python -m lifezen run --dry-run # prova senza pubblicare
""")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lifezen",
        description="Automazione contenuti Instagram per @lifezen77real — 365 giorni di zen.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Documentazione completa in README.md",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log dettagliati")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="genera e pubblica il contenuto del giorno")
    run.add_argument("--date", type=parse_date, help="data specifica (AAAA-MM-GG)")
    run.add_argument("--force", action="store_true", help="ripubblica anche se già fatto")
    run.add_argument("--dry-run", action="store_true", help="genera senza pubblicare")
    run.add_argument("--story", action="store_true", help="genera anche la versione 1080x1920")
    run.set_defaults(func=cmd_run)

    preview = sub.add_parser("preview", help="genera le card senza pubblicare")
    preview.add_argument("--date", type=parse_date, help="data di partenza")
    preview.add_argument("--next", type=int, default=1, help="quanti giorni generare (default 1)")
    preview.add_argument("--month", type=int, choices=range(1, 13), help="genera un mese intero")
    preview.add_argument("--year", type=int, help="anno per --month (default: anno corrente)")
    preview.add_argument("--story", action="store_true", help="genera anche le storie")
    preview.add_argument("--sheet", action="store_true", help="crea una griglia di anteprima")
    preview.add_argument("--columns", type=int, default=5, help="colonne della griglia")
    preview.add_argument("--thumb", type=int, default=320, help="dimensione miniature")
    preview.set_defaults(func=cmd_preview)

    backfill = sub.add_parser("publish-month", help="pubblica i giorni passati di un mese")
    backfill.add_argument("--month", type=int, required=True, choices=range(1, 13))
    backfill.add_argument("--year", type=int)
    backfill.add_argument("--all-days", action="store_true", help="includi anche i giorni futuri")
    backfill.add_argument("--force", action="store_true", help="ripubblica quelli già fatti")
    backfill.add_argument("--sleep", type=int, default=45, help="pausa fra un post e l'altro (secondi)")
    backfill.set_defaults(func=cmd_publish_month)

    doctor = sub.add_parser("doctor", help="diagnosi di configurazione e API")
    doctor.add_argument("--offline", action="store_true", help="salta le chiamate a Meta")
    doctor.add_argument("--date", type=parse_date)
    doctor.set_defaults(func=cmd_doctor)

    auth = sub.add_parser("auth", help="aiuti per token e ID account")
    auth.add_argument("action", choices=["exchange", "pages", "check"])
    auth.add_argument("--token", help="token breve (exchange) o token utente Facebook (pages)")
    auth.set_defaults(func=cmd_auth)

    check = sub.add_parser("check", help="valida la libreria dei contenuti")
    check.add_argument("--date", type=parse_date)
    check.set_defaults(func=cmd_check)

    gallery = sub.add_parser("gallery", help="crea una pagina HTML con le card dell'anno")
    gallery.add_argument("--year", type=int, help="anno da generare (default: corrente)")
    gallery.set_defaults(func=cmd_gallery)

    stats = sub.add_parser("stats", help="mostra la cronologia di pubblicazione")
    stats.set_defaults(func=cmd_stats)

    cron = sub.add_parser("cron", help="mostra la pianificazione consigliata")
    cron.add_argument("--timezone")
    cron.add_argument("--path", help="percorso del repository")
    cron.set_defaults(func=cmd_cron)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n  Interrotto dall'utente.")
        return 130
    except Exception as exc:
        logging.error("%s", exc)
        if getattr(args, "verbose", False):
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
