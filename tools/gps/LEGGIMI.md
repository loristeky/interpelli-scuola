# Dati per «Dove mi conviene fare le GPS?»

L'app confronta classe, fascia e punteggio dell'utente con i **bollettini di nomina GPS** pubblicati
dagli Uffici scolastici provinciali. Per ogni provincia, classe e fascia usa: quante nomine ci sono
state, il punteggio dell'ultimo nominato (la «soglia») e la posizione raggiunta. I dati stanno in
`assets/gps_data.json` e contengono **solo valori aggregati, nessun nome**.

Ora il file contiene Pescara, Chieti e L'Aquila (1° bollettino 2026/27).

## Aggiungere province o bollettini
1. Scarica il PDF del bollettino di nomina dal sito dell'Ufficio scolastico provinciale.
2. Serve il comando `pdftotext` (pacchetto *poppler-utils*; su Windows: poppler per Windows).
3. Esegui, aggiungendo ai dati esistenti:

       python tools/gps/build_gps_data.py bollettino_teramo.pdf --output assets/gps_data.json --aggiungi --bollettino 1

   La provincia si riconosce dai codici delle scuole (se non succede usa `--provincia TE`).
4. Ricostruisci l'app (Actions → Build AAB / APK).

I formati letti finora sono i tre PDF di esempio (Excel esportato in PDF con colonne, e
«Stampa in PDF» con una riga per classe). Altre province possono usare layout diversi: il comando
dice se non trova righe; in quel caso mandami il PDF e adatto il lettore.

## Limiti
- Il bollettino n. 1 è solo il primo giro: nei successivi si scende più in basso, quindi la soglia
  reale a fine anno è più bassa. La stima è prudente.
- Le nomine dipendono dai posti: una provincia con tante nomine offre più occasioni.
- Con poche nomine (1–2) la soglia è poco significativa: nell'app compare il numero di nomine.
- Fascia I e II hanno punteggi non confrontabili e sono tenute separate.

## Riserva servizio civile (15%)
La riserva copre **al massimo il 15% dei posti di quel turno, per classe di concorso**: l'algoritmo
scorre la graduatoria per punteggio e «salta» ai riservisti solo finché la quota non è raggiunta.
I bollettini non dicono chi sono i riservisti (colonne oscurate), quindi l'app mostra due soglie:

- **sicura**: punteggio dell'ultimo nominato dopo aver tolto il 15% dei punteggi più bassi (arrotondato
  per difetto, quindi con meno di 7 nomine non toglie nulla). Se il tuo punteggio la raggiunge, ci
  saresti anche con la quota piena → «Ci saresti».
- **minima**: punteggio dell'ultimo nominato in assoluto. Se la raggiungi ma non arrivi alla sicura →
  «Forse: dipende dalla riserva».

La percentuale è `GPS_RISERVA` in `main.py`. Ogni bollettino è un turno: per questo non vanno uniti
bollettini di turni diversi della stessa provincia (i PDF dello stesso turno, per esempio allegati A e B, sì).
