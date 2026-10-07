# Kaderkunde – Datenbank

Holt jede Nacht automatisch Kader und Spielerprofile von Transfermarkt und stellt sie der Kaderkunde-App bereit. Läuft kostenlos über GitHub Actions; ein eigener Server ist nicht nötig.

## Einrichtung (einmalig, ca. 10 Minuten)

1. **GitHub-Konto** anlegen (kostenlos), falls noch nicht vorhanden: https://github.com/signup
2. **Neues Repository** erstellen: https://github.com/new
   - Name z. B. `kaderkunde-daten`
   - Sichtbarkeit **Public** (siehe „Öffentlich oder privat?“ unten)
3. **Diese Dateien hochladen:** im neuen Repository auf „uploading an existing file“ klicken und den *Inhalt* dieses Ordners hineinziehen (inklusive des Ordners `.github`). Den Ordner `.github` zeigt der Datei-Explorer unter Windows/macOS evtl. nicht an – dann versteckte Dateien einblenden. Mit „Commit changes“ bestätigen.
4. **Schreibrechte für den Ablauf erlauben:** Settings → Actions → General → ganz unten „Workflow permissions“ → **Read and write permissions** → Save.
5. **Ersten Lauf starten:** Reiter **Actions** → „Transfermarkt-Daten aktualisieren“ → **Run workflow**.
6. **App verbinden:** In der Kaderkunde-App das Tweaks-Panel öffnen und bei **dataRepo** `DEIN-NAME/kaderkunde-daten` eintragen. Die App prüft dann regelmäßig auf neue Daten und lädt sie automatisch.

## Was passiert dabei?

- Jeder Lauf startet eine Kopie von [transfermarkt-api](https://github.com/felipeall/transfermarkt-api) und fragt darüber Transfermarkt ab – höflich, mit ca. 2 Abrufen pro Sekunde.
- **Erster Komplettdurchlauf:** alle Ligen aus `scraper/config.json` seit der Saison 1995/96 – Kader jeder Saison und danach jedes Spielerprofil mit Transfers, Ablösen und Marktwert-Verlauf. Das sind grob 200.000 Abrufe und dauert **ca. 2–4 Tage**. Der Ablauf läuft alle 6 Stunden je ~5,5 Stunden und macht dort weiter, wo er aufgehört hat. Die App kann die Daten schon während des Durchlaufs nutzen.
- **Danach** braucht ein Lauf nur noch wenige Minuten: aktuelle Kader neu, neue Spieler, aktive Spieler alle 7 Tage aufgefrischt. Dann kann der Zeitplan in `.github/workflows/update.yml` auf täglich gestellt werden (`"17 2 * * *"`).
- Ergebnis liegt im Branch **`data`** (Ordner `public/` für die App, `raw/` als Arbeitsstand). Der Branch wird jedes Mal ohne Verlauf neu geschrieben, damit das Repository nicht anwächst.

## Ligen und Zeitraum anpassen

`scraper/config.json`:
- `competitions` – Transfermarkt-Kürzel der Ligen (stehen in der URL, z. B. `.../wettbewerb/L2` → `L2`). Neue Ligen einfach ergänzen.
- `from_season` – erste Saison (Startjahr, 1995 = 1995/96).
- `requests_per_second` – nicht erhöhen; zu viele Abrufe führen zu Sperren.

## Öffentlich oder privat?

- **Public (empfohlen):** Actions-Minuten sind unbegrenzt kostenlos, und die App kann die Daten ohne Zugangsschlüssel laden. Die gesammelten Daten sind dann für jeden einsehbar, der das Repository findet.
- **Private:** GitHub schenkt 2.000 Actions-Minuten pro Monat. Der erste Komplettdurchlauf dauert dann mehrere Wochen (Zeitplan auf täglich stellen und `budget` im Workflow auf ~60 senken). Für die App unter Settings → Developer settings → *Fine-grained tokens* einen Token mit Lesezugriff („Contents: Read“) auf dieses eine Repository erstellen und in der App bei **dataToken** eintragen.

## Wenn etwas nicht klappt

- Reiter **Actions** → letzter Lauf → Protokoll ansehen.
- Startet die API nicht oder liefert nur Fehler: in der Workflow-Datei `TM_API_REF: main` auf eine ältere Release-Version setzen (Liste: https://github.com/felipeall/transfermarkt-api/releases).
- Felder fehlen in der App: lokal `python scraper/run.py --selftest` zeigt Beispielantworten der API; die Feldzuordnung steht in `scraper/run.py` (`fetch_player`, `stub_from_squad`).

## Hinweis

Transfermarkt untersagt in seinen Nutzungsbedingungen das automatisierte Auslesen. Dieses Projekt ist für die rein private Nutzung gedacht; die Daten nicht weiterverbreiten.
