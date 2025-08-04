# Tally List Integration

Diese benutzerdefinierte Integration für [Home Assistant](https://www.home-assistant.io/) wird über HACS bereitgestellt und hilft, Getränkezählungen für mehrere Personen zu verwalten. Alle Personen mit einem verknüpften Home-Assistant-Benutzerkonto werden automatisch importiert. Getränke werden einmal definiert und von allen gemeinsam genutzt.

Deutsch • [English](README.md)

## Funktionen

- Automatischer Import von Personen mit Benutzerkonten.
- Gemeinsame Getränkeliste mit Namen und Preis für jede Person.
- Sensoren für Getränkezählungen, Getränkepreise, einen Freibetrag und den Gesamtbetrag pro Person.
- Button-Entität zum Zurücksetzen aller Zähler einer Person; nur Nutzer mit Override-Rechten („Tally Admins") dürfen sie verwenden.
- Konfigurierbares Währungssymbol (Standard: €).
- Dienste zum Hinzufügen, Entfernen, Anpassen, Zurücksetzen und Exportieren von Zählern.
- Zähler können beim Entfernen eines Getränks nicht unter null fallen.
- Möglichkeit, Personen vom automatischen Import auszuschließen.
- Vergabe von Override-Rechten an ausgewählte Nutzer, damit sie für alle Getränke zählen können.

## Installation

1. Dieses Repository als benutzerdefiniertes Repository zu HACS hinzufügen.
2. Die **Tally List**-Integration installieren.
3. Home Assistant neu starten und die Integration über die Oberfläche hinzufügen.

## Verwendung

Beim ersten Einrichten wirst du nach verfügbaren Getränken gefragt. Alle Personen mit Benutzerkonto teilen sich diese Liste. Getränke und Preise können später über die Integrationsoptionen verwaltet werden.

### Dienste

- `tally_list.add_drink`: erhöht die Anzahl eines Getränks für eine Person.
- `tally_list.remove_drink`: verringert die Anzahl eines Getränks für eine Person (nie unter null).
- `tally_list.adjust_count`: setzt die Anzahl eines Getränks auf einen bestimmten Wert.
- `tally_list.reset_counters`: setzt alle Zähler für eine Person oder – ohne Angabe einer Person – für alle zurück.
- `tally_list.export_csv`: exportiert alle `_amount_due`-Sensoren als CSV-Dateien (`daily`, `weekly`, `monthly` oder `manual`), gespeichert unter `/config/backup/tally_list/<type>/`.

### Reset-Schalter

Jede Person erhält eine Entität `button.<person>_reset_tally`, um ihre Zähler zurückzusetzen. Nur Tally Admins dürfen sie betätigen.

## Preisliste und Sensoren

Alle Getränke werden in einer gemeinsamen Preisliste gespeichert. Ein spezieller Benutzer namens `Preisliste` stellt für jedes Getränk einen Preissensor sowie einen Sensor für den Freibetrag bereit, während normale Personen nur Zähl- und Gesamtbetragssensoren erhalten. Der Freibetrag wird vom Gesamtbetrag jeder Person abgezogen. Getränke, Preise und Freibetrag können jederzeit über die Integrationsoptionen bearbeitet werden.

## WebSocket-API

Der WebSocket-Befehl `tally_list/get_admins` gibt alle Benutzer mit Override-Rechten zurück und kann aus dem Home-Assistant-Frontend oder einem externen Client aufgerufen werden. Der Befehl erfordert einen authentifizierten Home-Assistant-Benutzer.

```js
await this.hass.connection.sendMessagePromise({ type: "tally_list/get_admins" });
```

Beispielantwort:

```json
{"id":42,"type":"result","success":true,"result":{"admins":["tablet_dashboard","Test","Test 2"]}}
```

## Danksagungen

Danke an die Home-Assistant-Community.

