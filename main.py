#!/usr/bin/env python3
"""
App Flet per la gestione degli interpelli, il calcolo delle riserve GPS (15% per CdC)
e la visualizzazione ottimizzata per Android con paginazione.
"""
import flet as ft
import sqlite3
import json
import re
import html
import ssl
import os
import time
import math
import threading
from datetime import datetime, date, timedelta
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.parse import urljoin
import xml.etree.ElementTree as ET


# ----------------------------------------------------------------------------
# Calcolo Riserva 15% per Classe di Concorso
# ----------------------------------------------------------------------------
def calcola_riserva_cdc(posti_totali: int, percentuale: float = 0.15) -> dict:
    """
    Calcola il numero di posti destinati alla riserva (es. 15%) per una specifica
    classe di concorso in base al numero di nomine/posti disponibili.
    
    Esempio: su 20 posti ADMM -> 20 * 0.15 = 3.0 posti riservati.
    """
    if posti_totali <= 0:
        return {
            "posti_totali": 0,
            "posti_riserva": 0,
            "posti_ordinari": 0,
            "percentuale": percentuale
        }
    
    posti_riserva_raw = posti_totali * percentuale
    posti_riserva = math.floor(posti_riserva_raw + 0.5)  # Arrotondamento all'intero più vicino
    posti_riserva = min(posti_riserva, posti_totali)
    posti_ordinari = posti_totali - posti_riserva
    
    return {
        "posti_totali": posti_totali,
        "posti_riserva": posti_riserva,
        "posti_ordinari": posti_ordinari,
        "percentuale": percentuale
    }


# ----------------------------------------------------------------------------
# Fonti (uffici scolastici provinciali/regionali)
# ----------------------------------------------------------------------------
PAGES_TO_FETCH = 5

ATA_KEYWORDS = [
    "ata", "dsga", "direttore dei servizi generali", "collaboratore scolastico", 
    "collaboratori scolastici", "assistente amministrativo", "assistenti amministrativi",
    "assistente tecnico", "assistenti tecnici", "operatore scolastico", "operatori scolastici",
    "operatore dei servizi agrari", "addetto aziende agrarie", "cuoco", "cuochi",
    "infermiere", "infermieri", "guardarobiere", "guardarobieri"
]

SOURCES = {
    "Abruzzo": [
        ("USP Chieti e Pescara", "https://www.istruzionechietipescara.it/category/interpelli-provinciali/feed/", 1),
        ("USP Teramo", "https://www.csateramo.it/wpusp/interpelli", 1),
        ("USP L'Aquila", "https://www.uspuquila.it/category/interpelli/feed/", 1)
    ],
    "Basilicata": [
        ("USP Matera", "https://www.istruzionematera.it/category/interpelli/feed/", 1),
        ("USP Potenza", "https://www.usppotenza.it/category/interpelli/feed/", 1)
    ],
    "Calabria": [
        ("USP Reggio Calabria", "https://www.usprc.it/category/interpelli/feed/", 1),
        ("USP Catanzaro", "https://www.uspcatanzaro.it/category/interpelli/feed/", 1),
        ("USP Cosenza", "https://www.uspcosenza.it/category/interpelli/feed/", 1)
    ],
    "Campania": [
        ("USP Caserta", "https://www.atpcaserta.it/category/interpelli/feed/", 1),
        ("USP Salerno", "https://www.atpsalerno.it/category/interpelli/feed/", 1),
        ("USP Napoli", "https://www.ustnapoli.it/category/interpelli/feed/", 1)
    ],
    "Emilia-Romagna": [
        ("USP Bologna", "https://interpelloweb.it/interpelli-supplenze/istituto/boss000vd8/", 1),
        ("USP Ferrara", "https://fe.istruzioneer.gov.it/category/interpelli_docenti/", 1),
        ("USP Modena", "https://mo.istruzioneer.gov.it/category/interpelli-personale-docente-2026-27/", 1),
        ("USP Parma", "https://pr.istruzioneer.gov.it/interpelli-docenti/", 1),
        ("USP Reggio Emilia", "https://re.istruzioneer.gov.it/tutte-le-notizie/", 1),
        ("USP Forlì Cesena", "https://fc.istruzioneer.gov.it/category/interpelli-a-s-2026-27/", 1),
        ("USP Piacenza", "https://pc.istruzioneer.gov.it/interpelli/", 1),
        ("USP Ravenna", "https://ra.istruzioneer.gov.it/conferimento-supplenze-per-esaurimento-graduatorie-di-istituto/", 1),
        ("USP Rimini", "https://rn.istruzioneer.gov.it/category/personale-docente/interpelli-docenti-2026-2027/", 1)
    ],
    "Friuli-Venezia Giulia": [
        ("USP Trieste", "https://usrfvg.gov.it/it/home/menu/uffici/ufficio-territoriale-di-trieste/Interpelli/index.html", 1),
        ("USP Udine", "https://usrfvg.gov.it/it/home/menu/uffici/ufficio-territoriale-di-udine/Interpelli/index.html", 1),
        ("USP Gorizia", "https://usrfvg.gov.it/it/home/menu/uffici/ufficio-territoriale-di-gorizia/Interpelli/", 1),
        ("USP Pordenone", "https://usrfvg.gov.it/it/home/menu/uffici/ufficio-territoriale-di-pordenone/Interpelli/index.html", 1)
    ],
    "Lazio": [
        ("USP Frosinone", "https://www.atpfrosinone.it/category/interpelli/feed/", 1),
        ("USP Latina", "https://www.csalatina.it/category/interpelli/feed/", 1),
        ("USP Roma", "https://www.atpromaistruzione.it/atp/category/interpelli/feed/", 1),
        ("USP Viterbo", "https://www.uspviterbo.it/category/interpelli/feed/", 1)
    ],
    "Liguria": [
        ("USP Genova", "https://servizi.istruzioneliguria.gov.it/provincia.php?provincia=GE", 1),
        ("USP La Spezia", "https://servizi.istruzioneliguria.gov.it/provincia.php?p=SP", 1),
        ("USP Imperia", "https://www.istruzioneimperia.gov.it/pagine/interpelli-e-comunicati", 1),
        ("USP Savona", "https://www.istruzionesavona.gov.it/pagine/interpelli-e-comunicati", 1)
    ],
    "Lombardia": [
        ("USP Milano", "https://www.mim.gov.it/web/milano/interpelli-ricerca-supplenti", 1),
        ("USP Brescia", "https://www.mim.gov.it/web/brescia/interpelli-ricerca-supplenti", 1),
        ("USP Bergamo", "https://www.mim.gov.it/web/bergamo/interpelli-ricerca-supplenti", 1),
        ("USP Como", "https://www.mim.gov.it/web/como/interpelli-ricerca-supplenti", 1),
        ("USP Cremona", "https://www.mim.gov.it/web/cremona/interpelli-ricerca-supplenti", 1),
        ("USP Lecco", "https://www.mim.gov.it/web/lecco/interpelli-ricerca-supplenti", 1),
        ("USP Lodi", "https://www.mim.gov.it/web/lodi/interpelli-ricerca-supplenti", 1),
        ("USP Mantova", "https://www.mim.gov.it/web/mantova/interpelli-ricerca-supplenti", 1),
        ("USP Monza brianza", "https://www.mim.gov.it/web/monza-brianza/interpelli-ricerca-supplenti", 1),
        ("USP Pavia", "https://www.mim.gov.it/web/pavia/interpelli-ricerca-supplenti", 1),
        ("USP Sondrio", "https://www.mim.gov.it/web/sondrio/interpelli-ricerca-supplenti", 1),
        ("USP Varese", "https://www.mim.gov.it/web/varese/interpelli-ricerca-supplenti", 1)
    ],
    "Marche": [
        ("USP Ancona", "https://www.uspancona.it/category/interpelli/feed/", 1),
        ("USP Macerata", "https://www.uspmacerata.it/category/interpelli/feed/", 1)
    ],
    "Molise": [
        ("USP Campobasso", "https://www.uspcampobasso.it/category/interpelli/feed/", 1)
    ],
    "Piemonte": [
        ("USP Torino", "https://www.istruzionepiemonte.it/torino/interpelli-supplenze/", PAGES_TO_FETCH),
        ("USP Cuneo", "https://www.istruzionepiemonte.it/cuneo/category/interpelli/feed/", 1),
        ("USP Novara", "https://www.istruzionepiemonte.it/novara/category/interpelli/feed/", 1)
    ],
    "Puglia": [
        ("USP Bari", "https://www.uspbari.it/category/interpelli/feed/", 1),
        ("USP Foggia", "https://www.fg.usrpuglia.gov.it/category/interpelli/feed/", 1),
        ("USP Lecce", "https://www.usplecce.it/category/interpelli/feed/", 1),
        ("USP Taranto", "https://www.usptaranto.it/category/interpelli/feed/", 1)
    ],
    "Sardegna": [
        ("USP Cagliari", "https://www.uspcagliari.it/category/interpelli/feed/", 1),
        ("USP Sassari", "https://www.uspsassari.it/category/interpelli/feed/", 1)
    ],
    "Sicilia": [
        ("USP Agrigento", "https://ag.usr.sicilia.it/category/interpelli/feed/", 1),
        ("USP Caltanissetta-Enna", "https://cl-en.usr.sicilia.it/category/interpelli/feed/", 1),
        ("USP Catania", "https://ct.usr.sicilia.it/category/interpelli/feed/", 1),
        ("USP Palermo", "https://pa.usr.sicilia.it/category/interpelli/feed/", 1),
        ("USP Siracusa", "https://sr.usr.sicilia.it/category/interpelli/feed/", 1),
        ("USP Trapani", "https://tp.usr.sicilia.it/category/interpelli/feed/", 1)
    ],
    "Toscana": [
        ("USP Firenze", "https://www.toscana.istruzione.it/category/usp-firenze/interpelli/feed/", 1),
        ("USP Lucca", "https://www.toscana.istruzione.it/category/usp-lucca/interpelli/feed/", 1),
        ("USP Pisa", "https://www.toscana.istruzione.it/category/usp-pisa/interpelli/feed/", 1)
    ],
    "Trentino-Alto Adige": [
        ("USP Trento", "https://www.vivoscuola.it/feed/", 1)
    ],
    "Umbria": [
        ("USP Perugia", "https://www.usp.perugia.it/category/interpelli/feed/", 1)
    ],
    "Valle d'Aosta": [
        ("USP Aosta", "https://www.scuole.vda.it/category/interpelli/feed/", 1)
    ],
    "Veneto": [
        ("USP Padova", "https://padova.istruzioneveneto.gov.it/category/interpelli-personale-docente/", 1),
        ("USP Treviso", "https://treviso.istruzioneveneto.gov.it/tag/interpelli-istituti-scolastici/", 1),
        ("USP Venezia", "https://venezia.istruzioneveneto.gov.it/interpelli-supplenze/", 1),
        ("USP Verona", "https://verona.istruzioneveneto.gov.it/index.php/interpelli-as-2025-2026/", 1)
    ]
}


# ----------------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------------
MAX_WORKERS = 15
PAGE_SIZE = 25          # interpelli mostrati per "blocco"
DB_VERSION = 6          # alzare per forzare il rifacimento della cache
GPS_TOOL_URL = "https://punteggiogps.it/"
GPS_LISTS_URL = "https://www.orizzontescuola.it/gps-docenti-2026-27-ecco-le-prime-graduatorie-in-aggiornamento/"
SOON_DAYS = 3           # "in scadenza" = scade entro questi giorni

MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

BRAND_DARK = "#1C248C"
BRAND_LIGHT = "#347CF6"
GOLD = "#FFC83D"
GREEN = "#16A363"


def get_db_path():
    db_dir = os.getenv("FLET_APP_STORAGE_DATA")
    if not db_dir:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = "."
        db_dir = os.path.join(base_dir, "data")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "interpelli_nazionali.db")


DB = get_db_path()


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(DB, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return conn


def init_db():
    conn = db_connect()
    c = conn.cursor()
    version = c.execute("PRAGMA user_version").fetchone()[0]
    if version < DB_VERSION:
        c.execute("DROP TABLE IF EXISTS interpelli")
        c.execute(f"PRAGMA user_version = {DB_VERSION}")
    c.execute("""CREATE TABLE IF NOT EXISTS interpelli (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        url TEXT UNIQUE,
        region TEXT,
        source TEXT,
        target TEXT,
        published TEXT,
        deadline TEXT,
        cdc TEXT,
        post_type TEXT,
        doc_url TEXT,
        email TEXT,
        verified INTEGER DEFAULT 0
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_interpelli_published ON interpelli(published DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_interpelli_region ON interpelli(region)")
    conn.commit()
    conn.close()


def known_urls():
    try:
        conn = db_connect()
        rows = conn.execute("SELECT url FROM interpelli").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except sqlite3.Error:
        return set()


# ----------------------------------------------------------------------------
# Download e analisi delle pagine
# ----------------------------------------------------------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'<(script|style|noscript)\b.*?</\1>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', text))).strip()


def _open(url, context=None):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"})
    with urlopen(req, timeout=10, context=context) as resp:
        raw = resp.read(2_000_000)
        return raw.decode(resp.headers.get_content_charset() or 'utf-8', errors='replace')


def fetch_url(url):
    try:
        return _open(url, ssl.create_default_context())
    except Exception as ex:
        reason = getattr(ex, "reason", ex)
        if isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(ex).upper():
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return _open(url, ctx)
        raise


MESI_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
    "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8,
    "set": 9, "sett": 9, "ott": 10, "nov": 11, "dic": 12,
}
_MESI_RE = "|".join(sorted(MESI_IT, key=len, reverse=True))
DATE_NUM = r"\d{1,2}\s?[\/\-.]\s?\d{1,2}\s?[\/\-.]\s?(?:\d{4}|\d{2})(?!\d)"
DATE_TXT = rf"\d{{1,2}}\s?(?:°|º)?\s+(?:{_MESI_RE})\b\.?(?:\s*,?\s*(?:\d{{4}}|\d{{2}}(?!\d)))?"
DATE_ANY = rf"(?:{DATE_NUM}|{DATE_TXT})"


def _mk(year, month, day):
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_date(value, default_year=None):
    if not value:
        return None
    value = value.strip()
    if re.match(r"^[A-Za-z]{3},", value):
        try:
            return parsedate_to_datetime(value).strftime("%Y-%m-%d")
        except Exception:
            pass

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if iso:
        return _mk(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    m = re.search(r"(\d{1,2})\s?[\/\-.]\s?(\d{1,2})\s?[\/\-.]\s?(\d{4}|\d{2})(?!\d)", value)
    if m:
        day, month, year = m.groups()
        year = int(year) + (2000 if len(year) == 2 else 0)
        return _mk(year, int(month), int(day))

    m = re.search(rf"(\d{{1,2}})\s?(?:°|º)?\s+({_MESI_RE})\b\.?(?:\s*,?\s*(\d{{4}}|\d{{2}}(?!\d)))?", value, re.I)
    if m:
        day, mese, year = m.groups()
        if year:
            year = int(year) + (2000 if len(year) == 2 else 0)
        else:
            year = default_year or date.today().year
        return _mk(year, MESI_IT[mese.lower()], int(day))

    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return None


# --- scadenza -----------------------------------------------------------------
_KEY = (r"(?:entro(?:\s+e\s+non\s+oltre)?|non\s+oltre|scadenz[ae]|termine(?:\s+ultimo)?|"
        r"improrogabilmente|presentat[ae]\s+(?:dal\s+\S+\s+)?al)")
_NOSTOP = r"(?:(?!\.\s)(?!\n).)"
DEADLINE_RE = re.compile(rf"({_KEY})({_NOSTOP}{{0,110}}?)({DATE_ANY})", re.I | re.S)
APPLY_WORDS = re.compile(r"domand|candidatur|disponibilit|istanz|present|invia|trasmett|pervenir|"
                         r"comunicar|manifest|aspirant|\bMAD\b|aderir|adesion", re.I)
CONTRACT_WORDS = re.compile(r"supplenz|incaric|contratt|nomina|assunzion|servizio|durata|"
                            r"fino\s+al|sino\s+al|termine\s+delle\s+(?:lezioni|attivit)", re.I)


def find_deadline(text, published=None):
    pub = datetime.strptime(published, "%Y-%m-%d") if published else None
    default_year = pub.year if pub else date.today().year
    best = None
    for m in DEADLINE_RE.finditer(text):
        key, between, raw = m.group(1), m.group(2), m.group(3)
        iso = parse_date(raw, default_year)
        if not iso:
            continue
        d = datetime.strptime(iso, "%Y-%m-%d")
        if pub and not re.search(r"\d{4}|/\d{2}\b|\.\d{2}\b", raw) and (pub - d).days > 30:
            iso = _mk(d.year + 1, d.month, d.day) or iso
            d = datetime.strptime(iso, "%Y-%m-%d")

        before = text[max(0, m.start() - 90):m.start()]
        context = before + key + between
        score = 0
        if APPLY_WORDS.search(context):
            score += 3
        if re.search(r"\bore\b|\d{1,2}[:.]\d{2}", between):
            score += 2
        if re.match(r"(?i)entro|non\s+oltre|scadenz", key):
            score += 1
        if CONTRACT_WORDS.search(before[-45:] + key + between[:25]) and not APPLY_WORDS.search(context):
            score -= 3
        if d.month in (6, 8) and d.day in (30, 31) and score < 4:
            score -= 2
        if pub:
            delta = (d - pub).days
            if delta < -1:
                score -= 3
            elif delta > 150:
                score -= 2
        if score >= 1 and (best is None or score > best[0]):
            a = max(0, m.start() - 25)
            snippet = text[a:m.end() + 25].strip()
            best = (score, iso, snippet)
    if best:
        return best[1], best[2]
    return None, ""


# --- pubblicazione ---------------------------------------------------------------
_META_PUB = [
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|datePublished|date|dc\.date(?:\.issued)?|'
    r'dcterms\.(?:created|issued|date)|og:article:published_time)["\'][^>]*content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:article:published_time|datePublished|date)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
]
PUB_TEXT_RE = re.compile(
    rf"(?:pubblicat[oa](?:\s+(?:il|in\s+data|data|sul\s+sito))?|data\s+(?:di\s+)?pubblicazione|"
    rf"pubblicazione|inserit[oa]\s+il|data\s+inserimento)\s*:?\s*(?:[A-Za-zàèéìòù]+\s+)?({DATE_ANY})", re.I)


def find_published(page_html, main_html, text):
    for pat in _META_PUB:
        m = re.search(pat, page_html, re.I | re.S)
        if m:
            iso = parse_date(m.group(1))
            if iso:
                return iso, "metadati della pagina"
    for m in re.finditer(r'<time\b([^>]*)>', main_html, re.I):
        attrs = m.group(1)
        dt = re.search(r'datetime=["\']([^"\']+)["\']', attrs, re.I)
        if dt and not re.search(r'updated|modified', attrs, re.I):
            iso = parse_date(dt.group(1))
            if iso:
                return iso, "data indicata nella pagina"
    m = PUB_TEXT_RE.search(text)
    if m:
        iso = parse_date(m.group(1))
        if iso:
            return iso, "testo dell'avviso"
    return None, ""


def main_region(page_html):
    h = re.sub(r'<(script|style|noscript)\b.*?</\1>', ' ', page_html, flags=re.I | re.S)
    arts = re.findall(r'<article\b.*?</article>', h, flags=re.I | re.S)
    if arts:
        return max(arts, key=len)
    m = re.search(r'<(?:div|section)\b[^>]*class=["\'][^"\']*(?:entry-content|post-content|article-body|'
                  r'node__content|field--name-body|contenuto|content-main)[^"\']*["\'][^>]*>', h, re.I)
    if m:
        return h[m.start():m.start() + 40000]
    mains = re.findall(r'<main\b.*?</main>', h, flags=re.I | re.S)
    if mains:
        return max(mains, key=len)
    return strip_chrome(h)


def strip_chrome(h):
    h = re.sub(r'<(script|style|noscript)\b.*?</\1>', ' ', h, flags=re.I | re.S)
    for tag in ("nav", "header", "footer", "aside"):
        h = re.sub(rf'<{tag}\b.*?</{tag}>', ' ', h, flags=re.I | re.S)
    return h


def analyze_post_content(full_text):
    text = full_text.lower()
    post_type = "Posto Ordinario / Altro"

    if "sostegno" in text:
        post_type = "Posto di Sostegno"
    elif "spezzone" in text:
        post_type = "Spezzone Orario"
    elif "cattedra orario esterna" in text or re.search(r"\bcoe\b", text):
        post_type = "Cattedra Orario Esterna (COE)"
    elif "cattedra orario interna" in text or re.search(r"\bcoi\b", text):
        post_type = "Cattedra Orario Interna (COI)"
    elif "annuale" in text:
        post_type = "Annuale"
    return post_type


ATA_TITLE_RE = re.compile(
    r"(?:\bATA\b|\bA\.\s?T\.\s?A\.?|personale\s+ata|collaborator[ei]\s+scolastic[oi]|"
    r"assistent[ei]\s+(?:amministrativ|tecnic)\w*|amministrativ[oiae]|\bDSGA\b|"
    r"direttore\s+dei\s+servizi\s+generali|\bcuoc[oh]i?\b|\binfermier[ei]\b|\bguardarobier[ei]\b|"
    r"operator[ei]\s+scolastic\w*|operator[ei]\s+dei\s+servizi\s+agrari|"
    r"addett[oi]\s+(?:alle?\s+)?aziend\w*\s+agrar\w*|\bpersonale\s+amministrativo\b)", re.I)
ATA_BODY_RE = re.compile(
    r"(?:\bATA\b|\bA\.\s?T\.\s?A\.?|personale\s+ata|collaborator[ei]\s+scolastic[oi]|"
    r"assistent[ei]\s+(?:amministrativ|tecnic)\w*|\bDSGA\b|direttore\s+dei\s+servizi\s+generali|"
    r"\bcuoc[oh]i?\b|\binfermier[ei]\b|\bguardarobier[ei]\b|operator[ei]\s+scolastic\w*|"
    r"operator[ei]\s+dei\s+servizi\s+agrari|addett[oi]\s+(?:alle?\s+)?aziend\w*\s+agrar\w*)", re.I)

CDC_SPECIAL = ["ADMM", "ADSS", "ADEE", "ADAA", "AAAA", "EEEE", "EEEM", "PPPP"]
CDC_NAMES = {
    "PPPP": "Personale educativo",
    "EEEM": "Educazione motoria",
    "EEEE": "Primaria (posto comune)",
    "ADEE": "Sostegno primaria",
    "AAAA": "Infanzia (posto comune)",
    "ADAA": "Sostegno infanzia",
    "ADMM": "Sostegno sec. I grado",
    "ADSS": "Sostegno sec. II grado",
}
CDC_PHRASES = [
    (re.compile(r"personale\s+educativ\w*", re.I), "PPPP"),
    (re.compile(r"educazione\s+motoria|\bed\.?\s*motoria|insegnante\s+di\s+motoria", re.I), "EEEM"),
]
_CDC_SPECIAL_RE = re.compile(r"\b(" + "|".join(CDC_SPECIAL) + r")\b", re.I)
_CDC_CODE_RE = re.compile(r"\b(?<![A-Za-z0-9])([A-Z]\d{2,3}|[A-Z]{2}\d{2})(?![A-Za-z0-9])")
_CDC_BAD_PREFIX = ("L", "D", "N")


def _codes_in(text, limit=3):
    spans = [(m.start(), m.group(1).upper()) for m in _CDC_SPECIAL_RE.finditer(text)]
    for m in _CDC_CODE_RE.finditer(text):
        code = m.group(1)
        if code[0] in _CDC_BAD_PREFIX and code[1:].isdigit():
            continue
        if re.fullmatch(r"AR\d{2}", code):
            continue
        spans.append((m.start(), code))
    for rx, code in CDC_PHRASES:
        m = rx.search(text)
        if m:
            spans.append((m.start(), code))
    explicit = {m.group(1).upper() for m in _CDC_SPECIAL_RE.finditer(text)}
    ordered = []
    for _, code in sorted(spans):
        if code not in ordered:
            ordered.append(code)
    if "PPPP" in ordered and "EEEM" in ordered and "EEEM" not in explicit:
        ordered.remove("EEEM")
    return ordered[:limit]


def detect_cdc(title, body=""):
    codes = _codes_in(title or "")
    if not codes and body and not ATA_TITLE_RE.search(title or ""):
        codes = _codes_in(body[:2500], limit=2)
    return ", ".join(codes)


NOT_INTERPELLO_RE = re.compile(r"bollettin\w*|\bnomine\b", re.I)


def is_not_interpello(title):
    return bool(NOT_INTERPELLO_RE.search(title or ""))


DOC_WORDS_RE = re.compile(
    r"(?:personale\s+docente|\bdocent[ei]\b|\binsegnant[ei]\b|personale\s+educativ\w*|"
    r"\beducator[ei]\b|\beducatric[ei]\b|\bcl(?:asse|\.)?\s+di\s+concorso|\bcdc\b)", re.I)


def _first_doc_pos(text):
    pos = []
    m = DOC_WORDS_RE.search(text)
    if m:
        pos.append(m.start())
    m = _CDC_SPECIAL_RE.search(text)
    if m:
        pos.append(m.start())
    for m in _CDC_CODE_RE.finditer(text):
        code = m.group(1)
        if code[0] in _CDC_BAD_PREFIX and code[1:].isdigit():
            continue
        if re.fullmatch(r"AR\d{2}", code):
            continue
        pos.append(m.start())
        break
    return min(pos) if pos else None


_EDUCATIVO_RE = re.compile(r"\bPPPP\b|personale\s+educativ\w*", re.I)


def detect_target(title, body=""):
    title = title or ""
    if DOC_WORDS_RE.search(title) or _codes_in(title):
        return "DOCENTI"
    if ATA_TITLE_RE.search(title):
        return "ATA"

    head = (body or "")[:2500]
    if _EDUCATIVO_RE.search(head):
        return "DOCENTI"
    body_ata = ATA_BODY_RE.search(head)
    if not body_ata:
        return "DOCENTI"
    doc_pos = _first_doc_pos(head)
    if doc_pos is not None and doc_pos < body_ata.start():
        return "DOCENTI"
    if doc_pos is not None and DOC_WORDS_RE.search(head) and not re.search(r"\bATA\b", head):
        return "DOCENTI"
    return "ATA"


DOC_RE = re.compile(r'href=["\']([^"\']+\.(?:pdf|docx?|odt)(?:\?[^"\']*)?)["\']', re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def extract_doc_url(page_html, base_url):
    found = [urljoin(base_url, h) for h in DOC_RE.findall(page_html)]
    for u in found:
        if any(k in u.lower() for k in ["interpell", "supplenz", "avviso"]):
            return u
    return found[0] if found else ""


def extract_email(text):
    emails = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if e not in emails:
            emails.append(e)
    for e in emails:
        if e.endswith(".edu.it") or "istruzione.it" in e or "pec" in e:
            return e
    return emails[0] if emails else ""


FILE_EXT_RE = re.compile(r"\.(?:pdf|docx?|odt|xlsx?|zip)(?:\?.*)?$", re.I)


# ----------------------------------------------------------------------------
# Interfaccia Utente Flet (con Sezione Riserva 15% e Popup GPS Impaginato)
# ----------------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "Gestione Interpelli & Calcolo Riserva 15%"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    init_db()

    # Componenti UI per il Calcolatore del 15% sulla CdC
    cdc_input = ft.TextField(label="Classe di Concorso (es. ADMM, A028)", value="ADMM", width=250)
    nomine_input = ft.TextField(label="Posti / nomine chiamate", value="20", keyboard_type=ft.KeyboardType.NUMBER, width=250)
    risultato_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, color=BRAND_DARK)

    def calcola_riserva_click(e):
        try:
            totale = int(nomine_input.value.strip())
            cdc = cdc_input.value.strip().upper()
            res = calcola_riserva_cdc(totale, 0.15)
            
            risultato_text.value = (
                f"📊 Risultato per la CdC {cdc}:\n"
                f"• Posti totali chiamati: {res['posti_totali']}\n"
                f"• Posti Riservati (15%): {res['posti_riserva']}\n"
                f"• Posti Ordinari: {res['posti_ordinari']}"
            )
        except ValueError:
            risultato_text.value = "⚠️ Inserisci un numero valido di posti."
        page.update()

    btn_calcola = ft.ElevatedButton(
        "Calcola Riserva (15%)", 
        on_click=calcola_riserva_click,
        style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor=BRAND_LIGHT)
    )

    card_calcolatore = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column([
                ft.Text("🧮 Calcolo Riserva 15% su Classe di Concorso", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([cdc_input, nomine_input]),
                btn_calcola,
                ft.Divider(),
                risultato_text
            ])
        )
    )

    calcola_riserva_click(None)

    # Funzione per aprire il popup "Dove mi conviene fare le GPS?" con Paginazione per Android
    def apri_popup_gps(e):
        # Dati di esempio (sostituibili con i dati reali del DB o JSON)
        dati_risultati = [
            {"provincia": f"Provincia {i+1}", "dettaglio": f"Punteggio min: {50 + i} - Nomine: {10 + i}"} 
            for i in range(45)
        ]

        elementi_per_pagina = 7
        stato = {"pagina_attuale": 1}
        totale_pagine = math.ceil(len(dati_risultati) / elementi_per_pagina)

        largh_schermo = page.width if page.width < 600 else 550
        alt_schermo = page.height * 0.85

        lista_view = ft.ListView(expand=True, spacing=8)
        lbl_info_pagina = ft.Text("", size=14, weight=ft.FontWeight.W_500)
        btn_prev = ft.OutlinedButton("◀ Prec.")
        btn_next = ft.OutlinedButton("Succ. ▶")

        def aggiorna_vista_pagina():
            pagina = stato["pagina_attuale"]
            inizio = (pagina - 1) * elementi_per_pagina
            fine = inizio + elementi_per_pagina
            elementi_correnti = dati_risultati[inizio:fine]

            lista_view.controls.clear()
            for item in elementi_correnti:
                lista_view.controls.append(
                    ft.Card(
                        content=ft.ListTile(
                            leading=ft.Icon(ft.icons.LOCATION_ON, color=BRAND_LIGHT),
                            title=ft.Text(item["provincia"], weight=ft.FontWeight.BOLD),
                            subtitle=ft.Text(item["dettaglio"]),
                        ),
                        margin=ft.margin.only(bottom=4)
                    )
                )

            lbl_info_pagina.value = f"Pag. {pagina} di {totale_pagine}"
            btn_prev.disabled = (pagina == 1)
            btn_next.disabled = (pagina == totale_pagine)
            page.update()

        def prev_page(e):
            if stato["pagina_attuale"] > 1:
                stato["pagina_attuale"] -= 1
                aggiorna_vista_pagina()

        def next_page(e):
            if stato["pagina_attuale"] < totale_pagine:
                stato["pagina_attuale"] += 1
                aggiorna_vista_pagina()

        btn_prev.on_click = prev_page
        btn_next.on_click = next_page

        contenuto_popup = ft.Container(
            width=largh_schermo,
            height=alt_schermo,
            padding=15,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("📍 Dove conviene fare le GPS?", size=18, weight=ft.FontWeight.BOLD, color=BRAND_DARK),
                            ft.IconButton(icon=ft.icons.CLOSE, on_click=lambda _: chiudi_dialogo())
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Divider(height=1, color=ft.colors.GREY_300),
                    lista_view,
                    ft.Divider(height=1, color=ft.colors.GREY_300),
                    ft.Row(
                        [
                            btn_prev,
                            lbl_info_pagina,
                            btn_next
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ],
                expand=True
            )
        )

        dialogo = ft.AlertDialog(
            content=contenuto_popup,
            content_padding=0,
            shape=ft.RoundedRectangleBorder(radius=16)
        )

        def chiudi_dialogo():
            dialogo.open = False
            page.update()

        page.dialog = dialogo
        dialogo.open = True
        aggiorna_vista_pagina()

    btn_apri_gps = ft.ElevatedButton(
        "Dove mi conviene fare le GPS?",
        icon=ft.icons.MAP,
        on_click=apri_popup_gps,
        style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor=BRAND_LIGHT)
    )

    page.add(
        ft.Text("Interpelli & Calcolo Riserve GPS", size=24, weight=ft.FontWeight.BOLD, color=BRAND_DARK),
        card_calcolatore,
        ft.Divider(),
        btn_apri_gps
    )


if __name__ == "__main__":
    ft.app(target=main)
