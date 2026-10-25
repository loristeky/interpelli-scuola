# Aggiungere province: basta caricare i PDF qui

1. Scarica il bollettino di nomina GPS (PDF, oppure Excel .xlsx/.xlsm) dal sito dell'Ufficio scolastico provinciale.
2. Su GitHub apri questa cartella `bollettini` → **Add file → Upload files** → trascina i file → **Commit changes**.
   Il numero del turno si legge dal nome del file: se si chiama `...bollettino-2...pdf` è il turno 2,
   altrimenti è il turno 1. Se carichi il turno 2 di una provincia, si aggiunge al turno 1.
3. Dopo un minuto circa parte da sola l'automazione «Aggiorna dati GPS»: legge i PDF, aggiorna
   `assets/gps_data.json` e **cancella i PDF dalla cartella** (contengono nomi dei candidati).
4. Per avere i dati nell'app, ricostruisci l'app (Actions → Build APK / Build AAB).

Controlla il risultato in Actions → «Aggiorna dati GPS»: il registro elenca ogni file con provincia,
turno e numero di nomine, e segnala i file che non riesce a leggere (restano qui).

Formati letti: PDF a tabella, PDF a testo, PDF con righe CSV e fogli Excel. Il nome della provincia si riconosce dai codici
delle scuole; se mancano si usa il nome del file (es. `Ragusa1.pdf`). I PDF con le colonne spezzate su pagine diverse
e quelli senza punteggio non sono leggibili e vengono saltati con un avviso.
