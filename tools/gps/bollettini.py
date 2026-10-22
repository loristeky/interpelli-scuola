"""Lettura dei bollettini di nomina GPS (PDF) e aggregazione per provincia, classe e fascia.

Dei bollettini si usano SOLO: classe di concorso, tipo di graduatoria (GPS), fascia, posizione,
punteggio e codice scuola (per riconoscere la provincia). Nomi e altri dati personali non vengono
letti né salvati.
"""
import re
import subprocess

# Codice meccanografico (prime due lettere) -> (provincia, regione)
SIGLE = {
    "AG": ("Agrigento", "Sicilia"), "AL": ("Alessandria", "Piemonte"), "AN": ("Ancona", "Marche"),
    "AO": ("Aosta", "Valle d'Aosta"), "AP": ("Ascoli Piceno", "Marche"), "AQ": ("L'Aquila", "Abruzzo"),
    "AR": ("Arezzo", "Toscana"), "AT": ("Asti", "Piemonte"), "AV": ("Avellino", "Campania"),
    "BA": ("Bari", "Puglia"), "BG": ("Bergamo", "Lombardia"), "BI": ("Biella", "Piemonte"),
    "BL": ("Belluno", "Veneto"), "BN": ("Benevento", "Campania"), "BO": ("Bologna", "Emilia-Romagna"),
    "BR": ("Brindisi", "Puglia"), "BS": ("Brescia", "Lombardia"), "BT": ("Barletta-Andria-Trani", "Puglia"),
    "BZ": ("Bolzano", "Trentino-Alto Adige"), "CA": ("Cagliari", "Sardegna"), "CB": ("Campobasso", "Molise"),
    "CE": ("Caserta", "Campania"), "CH": ("Chieti", "Abruzzo"), "CL": ("Caltanissetta", "Sicilia"),
    "CN": ("Cuneo", "Piemonte"), "CO": ("Como", "Lombardia"), "CR": ("Cremona", "Lombardia"),
    "CS": ("Cosenza", "Calabria"), "CT": ("Catania", "Sicilia"), "CZ": ("Catanzaro", "Calabria"),
    "EN": ("Enna", "Sicilia"), "FC": ("Forlì-Cesena", "Emilia-Romagna"), "FE": ("Ferrara", "Emilia-Romagna"),
    "FG": ("Foggia", "Puglia"), "FI": ("Firenze", "Toscana"), "FM": ("Fermo", "Marche"),
    "FR": ("Frosinone", "Lazio"), "GE": ("Genova", "Liguria"), "GO": ("Gorizia", "Friuli-Venezia Giulia"),
    "GR": ("Grosseto", "Toscana"), "IM": ("Imperia", "Liguria"), "IS": ("Isernia", "Molise"),
    "KR": ("Crotone", "Calabria"), "LC": ("Lecco", "Lombardia"), "LE": ("Lecce", "Puglia"),
    "LI": ("Livorno", "Toscana"), "LO": ("Lodi", "Lombardia"), "LT": ("Latina", "Lazio"),
    "LU": ("Lucca", "Toscana"), "MB": ("Monza e Brianza", "Lombardia"), "MC": ("Macerata", "Marche"),
    "ME": ("Messina", "Sicilia"), "MI": ("Milano", "Lombardia"), "MN": ("Mantova", "Lombardia"),
    "MO": ("Modena", "Emilia-Romagna"), "MS": ("Massa-Carrara", "Toscana"), "MT": ("Matera", "Basilicata"),
    "NA": ("Napoli", "Campania"), "NO": ("Novara", "Piemonte"), "NU": ("Nuoro", "Sardegna"),
    "OR": ("Oristano", "Sardegna"), "PA": ("Palermo", "Sicilia"), "PC": ("Piacenza", "Emilia-Romagna"),
    "PD": ("Padova", "Veneto"), "PE": ("Pescara", "Abruzzo"), "PG": ("Perugia", "Umbria"),
    "PI": ("Pisa", "Toscana"), "PN": ("Pordenone", "Friuli-Venezia Giulia"), "PO": ("Prato", "Toscana"),
    "PR": ("Parma", "Emilia-Romagna"), "PT": ("Pistoia", "Toscana"), "PU": ("Pesaro e Urbino", "Marche"),
    "PV": ("Pavia", "Lombardia"), "PZ": ("Potenza", "Basilicata"), "RA": ("Ravenna", "Emilia-Romagna"),
    "RC": ("Reggio Calabria", "Calabria"), "RE": ("Reggio Emilia", "Emilia-Romagna"), "RG": ("Ragusa", "Sicilia"),
    "RI": ("Rieti", "Lazio"), "RM": ("Roma", "Lazio"), "RN": ("Rimini", "Emilia-Romagna"),
    "RO": ("Rovigo", "Veneto"), "SA": ("Salerno", "Campania"), "SI": ("Siena", "Toscana"),
    "SO": ("Sondrio", "Lombardia"), "SP": ("La Spezia", "Liguria"), "SR": ("Siracusa", "Sicilia"),
    "SS": ("Sassari", "Sardegna"), "SU": ("Sud Sardegna", "Sardegna"), "SV": ("Savona", "Liguria"),
    "TA": ("Taranto", "Puglia"), "TE": ("Teramo", "Abruzzo"), "TN": ("Trento", "Trentino-Alto Adige"),
    "TO": ("Torino", "Piemonte"), "TP": ("Trapani", "Sicilia"), "TR": ("Terni", "Umbria"),
    "TS": ("Trieste", "Friuli-Venezia Giulia"), "TV": ("Treviso", "Veneto"), "UD": ("Udine", "Friuli-Venezia Giulia"),
    "VA": ("Varese", "Lombardia"), "VB": ("Verbano-Cusio-Ossola", "Piemonte"), "VC": ("Vercelli", "Piemonte"),
    "VE": ("Venezia", "Veneto"), "VI": ("Vicenza", "Veneto"), "VR": ("Verona", "Veneto"),
    "VT": ("Viterbo", "Lazio"), "VV": ("Vibo Valentia", "Calabria"),
}

CLASS_RE = r"[A-Z]{1,2}[0-9A-Z]{2,3}"
# Codice meccanografico di una scuola: 2 lettere provincia + 2 lettere tipo + 5 cifre + 1 carattere
SCHOOL_RE = re.compile(r"\b([A-Z]{2})[A-Z]{2}[0-9]{5}[0-9A-Z]\b")
# Formato a colonne: classe, descrizione, TIPO GRADUATORIA (il primo GPS/GAE/GUI che segue), fascia, ... posizione, punteggio,
# inclusione con riserva (N-, S- o R-). Le righe «GUI» (elenco di utilizzo) non sono GPS e si scartano dopo.
ROW_LAYOUT = re.compile(
    r"^(?P<cdc>" + CLASS_RE + r")\s+-\s+.*?\s(?P<tipo>GPS|GAE|GUI)\s+F(?P<fascia>\d)\b(?P<rest>.*)")
POS_SCORE = re.compile(r"\s(?P<pos>\d{1,5})\s+(?P<score>\d{1,3}(?:[.,]\d{1,3})?)\s+[NSR]\s?-")
# formato con riga della classe e riga dei dati separate (pdftotext -raw)
CLASS_LINE = re.compile(r"^(?P<cdc>" + CLASS_RE + r")\s+-\s+\S")
ROW_RAW = re.compile(r"^(?P<tipo>GPS|GAE)\s+F(?P<fascia>\d)\s+(?P<pos>\d{1,5})\s+(?P<score>\d{1,3}(?:[.,]\d{1,3})?)\s")


def pdf_text(path, raw):
    cmd = ["pdftotext", "-raw" if raw else "-layout", path, "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _school_siglas(text):
    """Province dei codici scuola presenti nel testo (una per codice)."""
    return [m.group(1) for m in SCHOOL_RE.finditer(text) if m.group(1) in SIGLE]


def parse_rows(text):
    """Restituisce [(classe, fascia, posizione, punteggio)] per le righe GPS."""
    rows = []
    cur = None
    for line in text.splitlines():
        line = line.rstrip()
        m = ROW_LAYOUT.match(line) if line[:1].strip() else None
        if m:
            cur = None
            if m["tipo"] != "GPS":
                continue
            ps = POS_SCORE.search(m["rest"])
            if ps:
                rows.append((m["cdc"], "I" if m["fascia"] == "1" else "II",
                             int(ps["pos"]), float(ps["score"].replace(",", "."))))
            continue
        m = CLASS_LINE.match(line)
        if m:
            cur = m["cdc"]
            continue
        m = ROW_RAW.match(line)
        if m and cur and m["tipo"] == "GPS":
            rows.append((cur, "I" if m["fascia"] == "1" else "II",
                         int(m["pos"]), float(m["score"].replace(",", "."))))
    return rows


def pdf_date(path):
    """Data di creazione del PDF (YYYY-MM-DD) o None."""
    from datetime import datetime
    try:
        out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"^CreationDate:\s+(.+)$", out, re.M)
    if m:
        for fmt in ("%a %b %d %H:%M:%S %Y %Z", "%a %b %d %H:%M:%S %Y"):
            try:
                return datetime.strptime(m.group(1).strip(), fmt).date().isoformat()
            except ValueError:
                pass
    return None


def read_pdf(path):
    """Legge un bollettino. Restituisce (sigla_provincia, righe). Un bollettino riguarda una sola provincia:
    la sigla è quella più frequente tra i codici delle scuole."""
    best_rows, best_text = [], ""
    for raw in (False, True):
        text = pdf_text(path, raw)
        rows = parse_rows(text)
        if len(rows) > len(best_rows):
            best_rows, best_text = rows, text
    siglas = _school_siglas(best_text)
    sigla = max(set(siglas), key=siglas.count) if siglas else None
    return sigla, best_rows


def aggregate(rows_by_sigla):
    """rows_by_sigla: {sigla: [(classe, fascia, pos, punteggio), ...]}.
    Per provincia/classe/fascia salva: n nomine, punteggio minimo e massimo, posizione più bassa e
    l'elenco "s" dei nominati come [punteggio, posizione] in ordine di punteggio decrescente
    (nessun nome: serve a escludere la quota riservata, vedi main.py)."""
    provinces = {}
    for sigla, rows in rows_by_sigla.items():
        prov, reg = SIGLE[sigla]
        entry = provinces.setdefault(prov, {"regione": reg, "classi": {}})
        for cdc, fascia, pos, score in rows:
            e = entry["classi"].setdefault(f"{cdc}:{fascia}", {"n": 0, "min": score, "max": score, "pos": pos, "s": []})
            e["n"] += 1
            e["min"] = min(e["min"], score)
            e["max"] = max(e["max"], score)
            e["pos"] = max(e["pos"], pos)
            e["s"].append([score, pos])
    for entry in provinces.values():
        for e in entry["classi"].values():
            e["s"].sort(key=lambda x: (-x[0], x[1]))
    return provinces
