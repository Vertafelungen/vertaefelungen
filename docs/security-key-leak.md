# Security: Entfernte GCP-Service-Account-Keys

## Warum das Löschen in HEAD nicht reicht
Auch wenn die Datei im aktuellen Stand entfernt ist, bleibt sie in der Git-Historie
gespeichert. Das bedeutet, dass die Credentials weiterhin über alte Commits abrufbar
sind, solange die Historie nicht bereinigt wurde.

## Sofortmaßnahmen (außerhalb des Repos)
1. **GCP Console öffnen:** IAM & Admin → Service Accounts.
2. Betroffenen Service Account auswählen.
3. Reiter **Keys** öffnen.
4. Den kompromittierten Key **löschen** und bei Bedarf **neu erstellen**.

## Git-Historie bereinigen (optional, aber empfohlen)
Nutze das Script `tools/purge_leaked_key_from_history.sh`, um die Datei aus der
Historie zu entfernen. Das Script führt **keinen** Force-Push aus, sondern gibt
nur die erforderlichen Kommandos aus.

> ⚠️ Achtung: History-Rewrites erfordern einen koordinierten Force-Push und das
> Neuauschecken der Repos aller Mitwirkenden.

## GitHub Secrets setzen
Lege im Repository unter **Settings → Secrets and variables → Actions** folgendes
Secret an:

- `GOOGLE_SERVICE_ACCOUNT_JSON` → kompletter JSON-Inhalt des Service-Account-Keys

Die Workflows nutzen das Secret zur Laufzeit und schreiben es optional in eine
temporäre Datei auf dem Runner.
