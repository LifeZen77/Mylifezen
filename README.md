# myLifeZen 🌿 — automazione contenuti Instagram

Automazione completa per **@lifezen77real**: genera ogni giorno una card 1080×1080
con il pensiero zen del calendario (365 giorni: pensieri, aforismi, mantra,
manifestazioni, consigli pratici) e la **pubblica da sola su Instagram** tramite
Instagram Graph API.

```
 contenuto del giorno  →  card 1080×1080  →  upload su URL pubblico  →  pubblicazione IG
   (365 giorni JSON)        (Pillow)          (jsDelivr/Cloudinary)      (Graph API)
```

- **Libreria di 365 giorni già scritta** in italiano, divisa in 12 temi mensili
  (Il risveglio, Il cuore quieto, La semina, Il respiro, La fioritura, La luce,
  L'onda, Il silenzio, Il ritorno, Il lasciar andare, La gratitudine,
  La luce interiore) con un contenuto bonus per il 29 febbraio.
- **5 tipi di contenuto** con palette e stile dedicati: pensiero, aforisma,
  mantra, manifestazione, consiglio.
- **Design generato in locale**: 15 palette zen, font variabili Lora /
  Cormorant Garamond / Inter, cornici, alone luminoso, grana di carta.
- **Zero dipendenze pesanti**: solo `Pillow` e `requests`.
- **Pubblicazione automatica** alle 8 circa (ora italiana) via GitHub Actions,
  oppure con un cron locale.
- **Sicura**: stato di esecuzione salvato su file (nessun post duplicato),
  dry-run sempre disponibile, segreti mai nel repository.

---

## 1. Avvio rapido (5 minuti, senza pubblicare)

```bash
git clone https://github.com/LifeZen77/Mylifezen.git
cd Mylifezen
python3 -m pip install -r requirements.txt

# genera la card di oggi senza pubblicare
python -m lifezen run --dry-run

# guarda il risultato: output/cards/2026-09-27-*.jpg

# genera tutte le card dell'anno e una pagina HTML da sfogliare
python -m lifezen gallery --year 2026
# apri output/gallery/calendario-2026.html nel browser
```

Per vedere un mese intero in una griglia:

```bash
python -m lifezen preview --month 1 --year 2026 --sheet --columns 6
# anteprima in output/sheets/
```

---

## 2. Collegare Instagram (una volta sola, ~15 minuti)

Instagram permette la pubblicazione automatica **solo** ad account
**Business o Creator** collegati a una **Pagina Facebook**. Gli account personali
non hanno accesso alla Content Publishing API.

### 2.1 Prepara l'account

1. Converti `@lifezen77real` in account **Business** o **Creator** (app Instagram →
   Impostazioni → Account → Passa a un account professionale). Gratuito.
2. Crea (o usa) una **Pagina Facebook** — anche vuota, anche senza follower — e
   collegalà all'account Instagram (Impostazioni Instagram → Pagina collegata).

### 2.2 Crea l'app Meta

1. Vai su [developers.facebook.com](https://developers.facebook.com/apps) →
   **Crea app** → tipo **Business**.
2. Nel pannello dell'app aggiungi il prodotto **Instagram** (o *Facebook Login
   for Business*, a seconda della versione del pannello).
3. In **Impostazioni app → Base** copia `ID app` e `Chiave segreta app`:
   diventeranno `IG_APP_ID` e `IG_APP_SECRET`.
4. Sempre in **Impostazioni app → Base**, aggiungi l'URL dell'informativa privacy
   (può essere una pagina GitHub Pages o il tuo sito): è obbligatorio per il token
   a lunga durata.

### 2.3 Ottieni un token con i permessi giusti

Apri il **[Graph API Explorer](https://developers.facebook.com/tools/explorer/)**:

1. Seleziona la tua app nel menu in alto a destra.
2. In *Permissions* aggiungi:
   - `pages_show_list`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
   - `business_management` *(consigliato, serve in alcuni scenari)*
3. Premi **Generate Access Token** e autorizza: otterrai un **token breve**
   (valido ~1 ora).

Ora ricava l'ID dell'account Instagram e il token della Pagina:

```bash
python -m lifezen auth pages --token IL_TUO_TOKEN_BREVE
```

L'output è di questo tipo:

```
  • Pagina: myLifeZen
    ↳ Instagram: @lifezen77real — IG_USER_ID=178414xxxxxxxxxxx (1523 follower)
    IG_ACCESS_TOKEN=EAAG... (token della Pagina, già a lunga durata)
```

### 2.4 Trasforma il token in uno a lunga durata (60 giorni)

```bash
python -m lifezen auth exchange --token IL_TUO_TOKEN_BREVE
```

Copia i valori nel file di configurazione:

```bash
cp .env.example .env
# poi modifica .env con IG_USER_ID e IG_ACCESS_TOKEN
```

### 2.5 Verifica che sia tutto pronto

```bash
python -m lifezen doctor
```

Il comando controlla calendario, credenziali, versione della Graph API
(con ripiego automatico se Meta ne ha ritirata una), quota giornaliera,
scadenza del token e fa un upload di prova verificando che l'immagine sia
raggiungibile pubblicamente. Se l'ultima riga dice **pronto a pubblicare ✓**
puoi lanciare la prima pubblicazione reale:

```bash
python -m lifezen run
```

> **Token della Pagina vs token utente.** L'`IG_ACCESS_TOKEN` ottenuto da
> `auth pages` è il token della Pagina: dura a lungo e resta valido finché non
> cambi password o revochi l'accesso. Un token utente a lunga durata dura
> invece 60 giorni: `python -m lifezen doctor` ti mostra la data di scadenza.

---

## 3. Hosting delle immagini

Instagram non accetta upload di file: **scarica l'immagine da un URL pubblico**.
Scegli la strategia con `LIFEZEN_IMAGE_HOST` nel `.env`:

| Valore | Come funziona | Serve |
|---|---|---|
| `github` *(default)* | il JPEG viene committato in `published/ANNO/MESE/` e servito da **jsDelivr CDN** | `LIFEZEN_REPO` + token con `contents:write` |
| `cloudinary` | upload semplice con preset *unsigned* o firma HMAC | `CLOUDINARY_CLOUD_NAME` + preset oppure key/secret |
| `imgbb` | upload semplice su imgbb.com | `IMGBB_API_KEY` |
| `dir` | copia in una cartella già servita dal tuo web server | `PUBLIC_BASE_URL` |

L'opzione `github` non richiede servizi esterni: il repository diventa sia
archivio che CDN. Nelle GitHub Actions il token `GITHUB_TOKEN` è già disponibile
con i permessi necessari (vedi `permissions: contents: write` nel workflow).

Prima di pubblicare, il codice verifica che l'URL risponda con un
`Content-Type: image/*` e, se jsDelivr non è raggiungibile, ripiega
automaticamente su `raw.githubusercontent.com`.

---

## 4. Automazione quotidiana

### 4.1 GitHub Actions (consigliata: nessun computer acceso)

Il workflow [`.github/workflows/daily-post.yml`](.github/workflows/daily-post.yml)
gira **ogni giorno alle 06:10 UTC** (≈ 08:10 ora italiana con l'ora legale,
07:10 con l'ora solare) e:

1. installa le dipendenze,
2. valida la libreria dei contenuti (`lifezen check`),
3. genera la card e la pubblica su Instagram,
4. salva le immagini come *artifact* del run (30 giorni),
5. registra l'esito in `data/state.json` con un commit `[skip ci]`.

**Configura i segreti** in *Settings → Secrets and variables → Actions → New repository secret*:

| Nome | Obbligatorio | Valore |
|---|---|---|
| `IG_USER_ID` | ✅ | ID account Instagram Business (da `auth pages`) |
| `IG_ACCESS_TOKEN` | ✅ | token di accesso |
| `IG_APP_ID` / `IG_APP_SECRET` | facoltativo | per il controllo di scadenza del token |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | facoltativo | notifica di esito su Telegram |

Puoi anche lanciarlo a mano da *Actions → Pubblicazione giornaliera → Run workflow*,
scegliendo una data specifica, la modalità dry-run, il force e la generazione
della versione storia.

Il secondo workflow, [`preview-month.yml`](.github/workflows/preview-month.yml),
genera tutte le card di un mese senza pubblicare: utile per approvare lo stile.

### 4.2 Cron locale

```bash
python -m lifezen cron --path /percorso/del/repo   # stampa le righe da incollare
crontab -e
```

```cron
0 8 * * *  cd /percorso/del/repo && /usr/bin/python3 -m lifezen run >> logs/lifezen.log 2>&1
```

### 4.3 Recuperare giorni passati

```bash
python -m lifezen publish-month --month 3 --year 2026 --sleep 60
```

Pubblica un giorno alla volta con una pausa (Instagram consente **50
pubblicazioni ogni 24 ore**). Di default salta quelli già pubblicati: aggiungi
`--force` per ripubblicarli.

---

## 5. Comandi

| Comando | Cosa fa |
|---|---|
| `python -m lifezen run` | genera e pubblica il contenuto di oggi |
| `python -m lifezen run --dry-run` | prepara tutto senza pubblicare |
| `python -m lifezen run --date 2026-03-01` | pubblica una data specifica |
| `python -m lifezen run --force --story` | ripubblica generando anche la storia 1080×1920 |
| `python -m lifezen preview --next 7` | genera le card dei prossimi 7 giorni |
| `python -m lifezen preview --month 4 --sheet` | mese intero + griglia di anteprima |
| `python -m lifezen gallery --year 2026` | pagina HTML con tutte le card dell'anno |
| `python -m lifezen publish-month --month 5` | recupera i giorni passati di un mese |
| `python -m lifezen doctor` | diagnosi completa (calendario, API, host, token) |
| `python -m lifezen auth pages --token …` | trova `IG_USER_ID` e token della Pagina |
| `python -m lifezen auth exchange --token …` | converte in token a lunga durata |
| `python -m lifezen check` | valida struttura e testi della libreria |
| `python -m lifezen stats` | cronologia delle pubblicazioni |
| `python -m lifezen cron` | pianificazione consigliata (Actions o cron) |

Aggiungi `-v` a qualsiasi comando per i log dettagliati.

---

## 6. Personalizzare i contenuti

Tutto il calendario editoriale vive in `assets/content/`:

```
assets/content/
├── common.json      # brand, tipi di contenuto, hashtag, temi mensili, bonus 29/02
├── month-01.json    # Gennaio — Il risveglio
├── month-02.json    # Febbraio — Il cuore quieto
├── ...
└── month-12.json    # Dicembre — La luce interiore
```

Ogni giorno ha questa forma:

```json
{
  "day": 15,
  "type": "consiglio",
  "title": "Il bicchiere d'acqua",
  "text": "Bevi un bicchiere d'acqua appena sveglio. Prima del caffè, prima del telefono.",
  "caption": "Un gesto fisico e concreto che dice al corpo: oggi mi prendo cura di te.",
  "tags": ["cura di sé", "mattina", "abitudini"]
}
```

- `type` deve essere uno di: `pensiero`, `aforisma`, `mantra`, `manifestazione`,
  `consiglio` — ognuno ha label, invito all'azione, palette e ornamento propri.
- `text` è il testo sulla card: usa `\n` per andare a capo (perfetto nei mantra).
  La dimensione del carattere si adatta automaticamente (da 72 pt a 34 pt).
- `caption` è il commento che accompagna il post su Instagram.
- `tags` diventano hashtag, ripuliti automaticamente (spazi, accenti e trattini
  non sono ammessi da Instagram). Le etichette ricorrenti si mappano in
  `hashtags.tag_map` di `common.json`.

Dopo una modifica:

```bash
python -m lifezen check                        # verifica struttura e lunghezze
python -m lifezen gallery --year 2026          # rivedi l'anno in HTML
```

Gli hashtag finali sono composti da: base (10) + tema del mese (2–3) + tag del
giorno, fino a un massimo di 15 — la combinazione ideale per non sembrare spam.

---

## 7. Personalizzare lo stile

In `lifezen/design.py`:

- `PALETTES`: 15 palette con sfondo, alone, inchiostro, colore tenue, accento,
  cornice. Aggiungerne una significa solo aggiungere una riga.
- `TYPE_PALETTES`: quali palette ruotano per ciascun tipo di contenuto.
- `SIZE`, `FRAME_INSET`, `CENTER_Y` in `lifezen/card.py`: geometria della card.

I font sono in `assets/fonts/` (licenza SIL Open Font License, file `OFL-*.txt`
inclusi). Per cambiare font sostituisci i `.ttf` mantenendo i nomi, oppure
modifica `FONT_FILES` e `AXES` in `design.py`. Il caricamento imposta i pesi
delle variabili per nome, quindi funziona anche con font con assi in ordine
diverso.

---

## 8. Notifiche (facoltative)

- **Telegram**: crea un bot con [@BotFather](https://t.me/BotFather), recupera il
  tuo `chat_id` e imposta `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Ricevi un
  messaggio a ogni pubblicazione con titolo, media ID e link al post.
- **Webhook**: imposta `LIFEZEN_WEBHOOK_URL` e riceverai un POST JSON con
  `date`, `status`, `media_id`, `permalink` — utile per collegare Zapier,
  n8n, Notion o un tuo backend.

---

## 9. Risoluzione dei problemi

| Messaggio | Significato e rimedio |
|---|---|
| `mancano IG_USER_ID, IG_ACCESS_TOKEN` | il `.env` non è compilato: vedi la sezione 2 |
| `Error validating access token` / codice `190` | token scaduto o revocato: rigeneralo con `auth pages` + `auth exchange` |
| `The Instagram account is not eligible` | l'account non è Business/Creator o non è collegato a una Pagina Facebook |
| `Only photo or video can be accepted as media type` | l'URL non punta a un JPEG/PNG raggiungibile: controlla l'host immagini con `doctor` |
| Container in stato `ERROR` | Instagram non è riuscito a scaricare l'immagine: verifica che l'URL sia pubblico (niente `localhost`), in HTTPS e senza redirect |
| `(#9007) Media già pubblicato` | lo stesso post è stato inviato due volte: usa `--force` solo se è intenzionale |
| Quota raggiunta (50/24h) | Instagram consente 50 pubblicazioni ogni 24 ore: `publish-month` aggiunge una pausa automatica |
| jsDelivr restituisce ancora la versione vecchia | è una cache CDN: il codice ripiega automaticamente su `raw.githubusercontent.com` |
| `Nessuna versione della Graph API ha risposto` | controlla la connessione o imposta `IG_GRAPH_VERSION` a una versione attiva |

Per un controllo completo in un colpo solo:

```bash
python -m lifezen doctor -v
```

---

## 10. Struttura del progetto

```
Mylifezen/
├── assets/
│   ├── content/            # libreria editoriale: 365 giorni in JSON
│   └── fonts/              # Lora, Cormorant Garamond, Inter + licenze OFL
├── lifezen/
│   ├── cli.py              # interfaccia a riga di comando
│   ├── config.py           # .env, ambiente, percorsi, segreti mascherati
│   ├── content.py          # caricamento calendario, caption, hashtag
│   ├── design.py           # palette, tipografia, primitive grafiche
│   ├── card.py             # rendering card 1080×1080 e storia 1080×1920
│   ├── gallery.py          # pagina HTML di revisione
│   ├── imagehost.py        # github / cloudinary / imgbb / dir
│   ├── instagram.py        # client Graph API (container → publish)
│   ├── pipeline.py         # orchestrazione della giornata
│   ├── state.py            # stato e cronologia (niente doppioni)
│   └── notify.py           # Telegram e webhook
├── tests/                  # 36 test: calendario, caption, rendering, pubblicazione
├── .github/workflows/      # automazione quotidiana e anteprime mensili
├── data/state.json         # cronologia delle pubblicazioni
├── published/              # JPEG pubblicati (serviti da jsDelivr)
├── output/                 # card e griglie generate in locale (non versionato)
├── .env.example            # modello di configurazione
└── requirements.txt
```

---

## 11. Test

```bash
python -m pytest tests/ -q
```

36 test coprono: completezza dei 365 giorni, lunghezza dei testi, validità degli
hashtag, limiti della caption, rendering delle card (dimensioni, peso, testo
estremo che non esce dalla cornice), storie 1080×1920, stato idempotente,
configurazione dell'hosting e **l'intero flusso di pubblicazione con una Graph
API simulata** (container, attesa, pubblicazione, registrazione, blocco dei
doppioni, dry-run che non chiama l'API).

---

## 12. Note e limiti

- La pubblicazione automatica richiede account **Instagram Business/Creator**
  collegato a una Pagina Facebook: è una regola di Meta, non una scelta del progetto.
- Limite di **50 pubblicazioni ogni 24 ore** per account.
- Il token a lunga durata va rinnovato periodicamente (`doctor` mostra la scadenza).
- Le immagini pubblicate finiscono in `published/`: se il repository è pubblico,
  restano visibili a chiunque (è proprio ciò che serve a Instagram). Non mettere
  materiale riservato tra i contenuti.
- Lo stato in `data/state.json` è la memoria del sistema: se cancelli quella voce,
  `run` potrebbe ripubblicare il contenuto del giorno.

---

<p align="center"><em>365 giorni, un pensiero alla volta.</em> ✦</p>
