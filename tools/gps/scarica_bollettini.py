#!/usr/bin/env python3
"""Scarica esclusivamente bollettini/esiti di turni di nomina GPS da fonti USP.

Le fonti sono quelle ufficiali censite in APP.SOURCES in main.py e le eventuali
pagine aggiuntive indicate in tools/gps/pagine_bollettini.json.
I PDF vengono scaricati nella cartella indicata e letti dal successivo passaggio
del workflow. Nel repository rimangono soltanto i dati statistici aggregati.
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from importlib import util
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
VISTI = Path(__file__).with_name("bollettini_visti.json")
EXTRA = Path(__file__).with_name("pagine_bollettini.json")

MAX_BYTES = 250_000_000
MAX_SECONDS = 600
MAX_DOWNLOADS = 150

APP = None

DOC_RE = re.compile(r"\.(pdf|xlsx|xlsm)(?:$|[?#])", re.I)

# Il titolo deve indicare un bollettino o un esito/turno di nomina.
TITLE_RE = re.compile(
    r"\bbollettin\w*\b|"
    r"\besit\w*\s+(?:del\s+)?(?:turno|nomine)\b|"
    r"\bturno\s+(?:n\.?\s*)?\d+\b|"
    r"\bnomine\s+(?:da\s+)?gps\b|"
    r"\bnomine\s+a\s+tempo\s+determinato\b",
    re.I,
)

GPS_RE = re.compile(
    r"\bgps\b|graduatori\w*\s+provincial\w*|supplenz\w*",
    re.I,
)

# Esclusioni: non scaricare questi tipi di pubblicazione.
SKIP_RE = re.compile(
    r"\bata\b|\bdsga\b|personale\s+ata|"
    r"collaborator\w*|assistent\w*|educativ\w*|"
    r"\bgae\b|ad\s+esaurimento|"
    r"immission\w*|\bin\s+ruolo|"
    r"concors\w*|interpell\w*|\bmad\b|"
    r"rettific\w*|errat\w*|"
    r"disponibilit\w*|convocazion\w*|"
    r"revoc\w*|integrazion\w*|"
    r"annullament\w*|sostituzion\w*|"
    r"mobilit\w*|assunzion\w*|"
    r"tempo\s+indeterminato|"
    r"posti\s+residu\w*|cattedre\s+disponibil\w*",
    re.I,
)

ESTERNI_NO = (
    "orizzontescuola.",
    "tecnicadellascuola.",
    "facebook.",
    "twitter.",
    "x.com",
    "whatsapp.",
    "t.me",
    "telegram.",
    "google.",
    "linkedin.",
    "instagram.",
    "youtube.",
    "mailto:",
    "wa.me",
)

NEWS_PATHS = (
    "",
    "feed/",
    "category/notizie/",
    "category/comunicazioni/",
    "category/news/",
    "category/avvisi/",
    "notizie/",
    "comunicazioni/",
    "category/comunicati/",
    "category/personale-docente/",
)


def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_app():
    """Carica main.py senza richiedere l'interfaccia grafica Flet."""
    os.environ.setdefault("FLET_APP_STORAGE_DATA", tempfile.mkdtemp())
    sys.modules.setdefault("flet", MagicMock())

    spec = util.spec_from_file_location("interpelli_app", ROOT / "main.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_site(url_a, url_b):
    """Accetta soltanto allegati ospitati sullo stesso dominio della pagina USP."""
    a = urlparse(url_a).netloc.lower().removeprefix("www.")
    b = urlparse(url_b).netloc.lower().removeprefix("www.")
    return bool(a and b and a == b)


def is_external(url):
    low = url.lower()
    return any(domain in low for domain in ESTERNI_NO)


def news_pages(sources):
    """Ricava pagine notizie/feed dallo stesso dominio delle fonti USP."""
    result = []
    seen = set()

    for name, url in sources:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue

        # Mantiene l'eventuale primo percorso degli USP su portali condivisi.
        segments = [x for x in parsed.path.split("/") if x]
        prefix = ""
        shared = (
            "istruzionepiemonte.it",
            "toscana.istruzione.it",
            "toscana-istruzione.it",
            "mim.gov.it",
        )
        if (
            segments
            and any(parsed.netloc.lower().endswith(x) for x in shared)
            and segments[0] not in ("category", "tag", "web", "feed")
        ):
            prefix = "/" + segments[0]

        base = f"{parsed.scheme}://{parsed.netloc}{prefix}/"
        for path in NEWS_PATHS:
            candidate = urljoin(base, path)
            if candidate not in seen:
                seen.add(candidate)
                result.append((name, candidate))

    return result


def load_sources(app):
    """Usa esclusivamente le fonti USP già censite nell'app."""
    sources = []

    for entries in app.SOURCES.values():
        for entry in entries:
            if len(entry) >= 2:
                name, url = entry[0], entry[1]
                if urlparse(url).scheme in ("http", "https"):
                    sources.append((str(name), str(url)))

    extras = read_json(EXTRA, [])
    for item in extras:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        name = item.get("nome", "USP")
        if (
            urlparse(url).scheme in ("http", "https")
            and item.get("tipo") != "elenco"
            and not is_external(url)
        ):
            sources.append((str(name), str(url)))

    # Elimina duplicati e domini editoriali.
    result = []
    seen = set()
    for name, url in sources:
        if is_external(url):
            continue
        key = (name, url)
        if key not in seen:
            seen.add(key)
            result.append((name, url))

    return result


def links_of(html, base):
    """Estrae titoli e link da una pagina HTML o da un feed."""
    found = []

    # Feed RSS/Atom.
    for item in re.findall(
        r"<item\b.*?</item>|<entry\b.*?</entry>",
        html,
        re.I | re.S,
    ):
        title = re.search(r"<title[^>]*>(.*?)</title>", item, re.I | re.S)
        link = (
            re.search(r"<link[^>]*>\s*([^<\s]+)\s*</link>", item, re.I)
            or re.search(r'<link[^>]*href=["\']([^"\']+)', item, re.I)
        )
        if title and link:
            found.append(
                (
                    clean(title.group(1)),
                    urljoin(base, unescape(link.group(1))),
                )
            )

    # Link nel corpo della pagina.
    body = re.sub(
        r"<(script|style|nav|footer|aside)\b.*?</\1>",
        " ",
        html,
        flags=re.I | re.S,
    )
    for href, label in re.findall(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        body,
        re.I | re.S,
    ):
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        found.append((clean(label), urljoin(base, unescape(href))))

    unique = []
    seen = set()
    for title, link in found:
        if link not in seen:
            seen.add(link)
            unique.append((title, link))
    return unique


def doc_links(html, base):
    """Trova allegati PDF/Excel, soltanto sul dominio della pagina USP."""
    result = []
    for href, label in re.findall(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        if not DOC_RE.search(href):
            continue

        url = urljoin(base, unescape(href))
        text = clean(label) + " " + unquote(url.rsplit("/", 1)[-1])

        if (
            not same_site(url, base)
            or is_external(url)
            or SKIP_RE.search(text)
        ):
            continue

        if url not in result:
            result.append(url)

    return result


def turn_of(title, fallback):
    """Ricava il numero del turno dal titolo."""
    roman = {
        "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
        "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
        "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    }

    match = re.search(
        r"\b(XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|IV|V|III|II|I)"
        r"\b\s*[°ºª]?\s*(?i:bollettino|turno)",
        title,
    )
    if match:
        return str(roman[match.group(1)])

    patterns = (
        r"boll\w*\s*(?:n\.?|numero|nr\.?)?\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*[°ºª]?\s*(?:turno|bollettino)\b",
        r"(?:turno|bollettino)\s*(?:n\.?\s*)?(\d{1,2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, title, re.I)
        if match and 1 <= int(match.group(1)) <= 30:
            return str(int(match.group(1)))

    return fallback


def valid_title(title):
    """Il titolo deve essere esplicitamente relativo a un turno GPS."""
    return bool(
        title
        and TITLE_RE.search(title)
        and GPS_RE.search(title)
        and not SKIP_RE.search(title)
    )


def download(url, destination):
    """Scarica un allegato pubblico rispettando robots.txt e limiti dimensionali."""
    import time

    if APP is not None and not APP.robots_allowed(url):
        return "download non consentito da robots.txt"

    request = Request(
        url,
        headers={
            "User-Agent": getattr(
                APP,
                "USER_AGENT",
                "Mozilla/5.0 (compatible; InterpelliScuola/1.0)",
            )
        },
    )

    contexts = [ssl.create_default_context()]
    insecure = ssl.create_default_context()
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    contexts.append(insecure)

    for context in contexts:
        try:
            total = 0
            started = time.time()
            first_bytes = b""

            with urlopen(request, timeout=60, context=context) as response:
                with open(destination, "wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        if not first_bytes:
                            first_bytes = chunk[:4]
                        total += len(chunk)

                        if total > MAX_BYTES:
                            raise ValueError("file oltre il limite di 250 MB")
                        if time.time() - started > MAX_SECONDS:
                            raise ValueError("download troppo lento")

                        output.write(chunk)

            if not (
                first_bytes.startswith(b"%PDF")
                or first_bytes.startswith(b"PK")
            ):
                raise ValueError("il file non è un PDF o un Excel")

            return None

        except ssl.SSLError:
            Path(destination).unlink(missing_ok=True)
            continue
        except Exception as error:
            Path(destination).unlink(missing_ok=True)
            return str(error)[:120]

    return "errore del certificato del sito"


def pdf_is_gps(path):
    """Controlla il testo del PDF: deve contenere riferimenti espliciti alle GPS."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        # Il formato Excel viene verificato dal parser durante l'elaborazione.
        return True

    try:
        result = subprocess.run(
            ["pdftotext", "-l", "5", path, "-"],
            capture_output=True,
            text=True,
            timeout=90,
        )
        text = result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False

    if not text.strip():
        # PDF scansionati: il parser successivo potrà provare l'OCR.
        return True

    if not re.search(
        r"\bgps\b|graduatori\w*\s+provincial\w*|supplenz\w*",
        text,
    ):
        return False

    if re.search(
        r"immission\w*\s+in\s+ruolo|"
        r"ad\s+esaurimento|\bgae\b|"
        r"tempo\s+indeterminato|"
        r"convocazion\w*|rettific\w*|"
        r"revoc\w*|disponibilit\w*|"
        r"interpell\w*",
        text,
    ):
        return False

    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cartella", default="bollettini")
    parser.add_argument("--prova", action="store_true")
    parser.add_argument("--max", type=int, default=MAX_DOWNLOADS)
    args = parser.parse_args(argv)

    global APP
    APP = load_app()

    state = read_json(VISTI, {"urls": [], "turni": {}, "origine": {}})
    seen = set(state.get("urls", []))
    counters = dict(state.get("turni", {}))
    origins = dict(state.get("origine", {}))

    sources = load_sources(APP)
    pages = sources + news_pages(sources)

    print(f"Fonti USP: {len(sources)}")
    print(f"Pagine ufficiali da controllare, inclusi feed e notizie: {len(pages)}")

    def scan(source):
        name, url = source
        try:
            html = APP.fetch_url(url)
        except Exception as error:
            return name, url, [], str(error)[:80]

        candidates = []
        for title, link in links_of(html, url):
            # Un link diretto a un PDF viene valutato usando il testo del link
            # e il nome dell'allegato; un articolo usando il proprio titolo.
            label = (title + " " + unquote(link.rsplit("/", 1)[-1])).strip()

            if is_external(link) or not same_site(link, url):
                continue
            if not valid_title(label):
                continue

            candidates.append((title or label, link))

        return name, url, candidates, None

    todo = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for name, page_url, candidates, error in executor.map(scan, pages):
            if error:
                print(f"[!] {name}: pagina non raggiungibile ({error})")
                continue

            for title, link in candidates:
                if link not in seen:
                    todo.append((name, page_url, title, link))

    # Elimina duplicati mantenendo l'ordine.
    unique = []
    candidate_seen = set()
    for item in todo:
        if item[3] not in candidate_seen:
            candidate_seen.add(item[3])
            unique.append(item)
    todo = unique

    print(f"Nuovi avvisi candidati: {len(todo)}")

    output_dir = Path(args.cartella)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0

    for name, page_url, title, link in todo:
        if downloaded >= args.max:
            break

        # Se il link è già un allegato, non serve aprire una seconda pagina.
        if DOC_RE.search(link):
            documents = [link]
        else:
            try:
                article = APP.fetch_url(link)
                documents = doc_links(article, link)
            except Exception as error:
                print(f"[!] Articolo non leggibile: {link}: {str(error)[:70]}")
                continue

        if not documents:
            # Non segna come visto: la pagina potrà essere ricontrollata.
            continue

        office = re.sub(
            r"^(USP|AT|UST|ATP)\s+",
            "",
            name,
            flags=re.I,
        )
        office_key = re.sub(r"[^A-Za-z0-9]+", "_", office).strip("_")
        turn = turn_of(title, None)

        for document in documents:
            if downloaded >= args.max:
                break
            if document in seen:
                continue

            if turn is None:
                counters[office_key] = counters.get(office_key, 0) + 1
                current_turn = str(counters[office_key])
            else:
                current_turn = turn
                counters[office_key] = max(
                    counters.get(office_key, 0),
                    int(current_turn),
                )

            extension = (
                ".xlsx"
                if re.search(r"\.xlsx?(?:$|[?#])|\.xlsm(?:$|[?#])", document, re.I)
                else ".pdf"
            )
            filename = f"{office_key}_bollettino-{current_turn}{extension}"
            destination = output_dir / filename

            suffix = 2
            while destination.exists():
                destination = output_dir / (
                    f"{office_key}_bollettino-{current_turn}_{suffix}{extension}"
                )
                suffix += 1

            if args.prova:
                print(f"[prova] {title} -> {destination.name}")
                continue

            error = download(document, str(destination))
            seen.add(document)

            if error:
                print(f"[!] {name}: {error}")
                continue

            if not pdf_is_gps(str(destination)):
                destination.unlink(missing_ok=True)
                print(f"[scartato] Non riconosciuto come bollettino GPS: {title}")
                continue

            origins[destination.name] = [link, document]
            downloaded += 1
            print(f"[OK] {name}: {title[:90]} -> {destination.name}")

        seen.add(link)

    if not args.prova:
        state = {
            "urls": sorted(seen)[-8000:],
            "turni": counters,
            "origine": dict(list(origins.items())[-600:]),
        }
        write_json(VISTI, state)

    print(f"Download completati: {downloaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
