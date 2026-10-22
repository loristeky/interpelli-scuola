#!/usr/bin/env python3
"""Prepara assets/gps_data.json per «Dove mi conviene fare le GPS?» dai bollettini di nomina GPS (PDF).

Per ogni provincia, classe di concorso e fascia salva: quante nomine, punteggio più basso e più alto
dei nominati, posizione più bassa raggiunta. Non vengono letti né salvati nomi o dati personali.
La provincia si riconosce dai codici delle scuole nel bollettino.

Uso (serve il comando `pdftotext`, pacchetto poppler-utils):
  python tools/gps/build_gps_data.py bollettino_pescara.pdf bollettino_chieti.pdf ... \\
         --output assets/gps_data.json --bollettino 1
  Per aggiungere province a un file già esistente:  ... --aggiungi
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bollettini  # noqa: E402


def default_year(today=None):
    today = today or date.today()
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y}/{(y + 1) % 100:02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", help="uno o più bollettini di nomina (PDF)")
    ap.add_argument("--output", default="assets/gps_data.json")
    ap.add_argument("--anno", default=default_year(), help="anno scolastico, es. 2026/27")
    ap.add_argument("--bollettino", default="1", help="numero del bollettino")
    ap.add_argument("--provincia", help="sigla (es. PE) se non si riconosce dai codici scuola; vale per tutti i PDF")
    ap.add_argument("--aggiungi", action="store_true", help="unisci ai dati già presenti nel file di output")
    args = ap.parse_args(argv)

    rows_by_sigla = {}
    dates = []
    for path in args.pdf:
        sigla, rows = bollettini.read_pdf(path)
        sigla = (args.provincia or sigla or "").upper()
        if sigla not in bollettini.SIGLE:
            print(f"{path}: provincia non riconosciuta (usa --provincia)", file=sys.stderr)
            return 1
        if not rows:
            print(f"{path}: nessuna riga GPS trovata", file=sys.stderr)
            return 1
        rows_by_sigla.setdefault(sigla, []).extend(rows)
        dates.append(bollettini.pdf_date(path))
        print(f"{os.path.basename(path)}: {bollettini.SIGLE[sigla][0]}, {len(rows)} nomine GPS")

    provinces = bollettini.aggregate(rows_by_sigla)
    if args.aggiungi and os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            old = json.load(f)
        merged = dict(old.get("province", {}))
        merged.update(provinces)
        provinces = merged
    data = {
        "anno": args.anno,
        "aggiornato": max([d for d in dates if d] or [date.today().isoformat()]),
        "bollettino": args.bollettino,
        "fonte": "Bollettini di nomina GPS pubblicati dagli Uffici scolastici provinciali",
        "province": dict(sorted(provinces.items())),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    pairs = sum(len(p["classi"]) for p in provinces.values())
    print(f"{len(provinces)} province, {pairs} classi/fasce -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
