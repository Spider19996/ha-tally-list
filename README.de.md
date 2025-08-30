# Tally List Integration

🇬🇧 [Read English version](README.md)

Diese benutzerdefinierte Integration für [Home Assistant](https://www.home-assistant.io/) wird über HACS bereitgestellt und hilft, Getränkezählungen für mehrere Personen zu verwalten. Alle Personen mit einem verknüpften Home-Assistant-Benutzerkonto werden automatisch importiert. Getränke werden einmal definiert und von allen gemeinsam genutzt.

## Funktionen

- Automatischer Import von Personen mit Benutzerkonten.
- Gemeinsame Getränkeliste mit Namen und Preis für jede Person.
- Sensoren für Getränkezählungen, Getränkepreise, einen Freibetrag und den Gesamtbetrag pro Person.
- Button-Entität zum Zurücksetzen aller Zähler einer Person; nur Nutzer mit Override-Rechten („Tally Admins") dürfen sie verwenden.
- Konfigurierbares Währungssymbol (Standard: €).
- Dienste zum Hinzufügen, Entfernen, Anpassen, Zurücksetzen, Exportieren von Zählern und zur Verwaltung persönlicher PINs (Tally-Admins können PINs für andere Nutzer setzen).
- Zähler können beim Entfernen eines Getränks nicht unter null fallen.
- Möglichkeit, Personen vom automatischen Import auszuschließen.
- Vergabe von Override-Rechten an ausgewählte Nutzer, damit sie für alle Getränke zählen können.
- Öffentliche Geräte können für alle Getränke zählen, wenn die PIN des Zielbenutzers angegeben wird.
- Optionaler Freigetränke-Modus mit eigenem Benutzer, Feed-Sensoren und konfigurierbarem Namen.

## Installation

1. Dieses Repository als benutzerdefiniertes Repository zu HACS hinzufügen.
2. Die **Tally List**-Integration installieren.
3. Home Assistant neu starten und die Integration über die Oberfläche hinzufügen.

Es ist empfehlenswert, zusätzlich die passende [Tally List Lovelace-Karte](https://github.com/Spider19996/ha-tally-list-lovelace) für eine entsprechende Dashboard-Ansicht zu installieren.

## Verwendung

Beim ersten Einrichten wirst du nach verfügbaren Getränken gefragt. Alle Personen mit Benutzerkonto teilen sich diese Liste. Getränke und Preise können später über die Integrationsoptionen verwaltet werden.

### Dienste

- `tally_list.add_drink`: erhöht die Anzahl eines Getränks für eine Person (schlägt fehl, wenn die Person nicht existiert; Anzahl kann angegeben werden).
- `tally_list.remove_drink`: verringert die Anzahl eines Getränks für eine Person (nie unter null; Anzahl kann angegeben werden).
- `tally_list.adjust_count`: setzt die Anzahl eines Getränks auf einen bestimmten Wert.
- `tally_list.reset_counters`: setzt alle Zähler für eine Person oder – ohne Angabe einer Person – für alle zurück.
- `tally_list.export_csv`: exportiert alle `_amount_due`-Sensoren als CSV-Dateien (`daily`, `weekly`, `monthly` oder `manual`), gespeichert unter `/config/backup/tally_list/<type>/`.
- `tally_list.set_pin`: setzt oder entfernt eine persönliche vierstellige PIN aus Ziffern für öffentliche Geräte (Admins können PINs für andere Nutzer setzen).

### Reset-Schalter

Jede Person erhält eine Entität `button.<person>_reset_tally`, um ihre Zähler zurückzusetzen. Nur Tally Admins dürfen sie betätigen.

## Preisliste und Sensoren

Alle Getränke werden in einer gemeinsamen Preisliste gespeichert. Ein spezieller Benutzer namens `Preisliste` (englisch `Price list`) stellt für jedes Getränk einen Preissensor sowie einen Sensor für den Freibetrag bereit, während normale Personen nur Zähl- und Gesamtbetragssensoren erhalten. Der Freibetrag wird vom Gesamtbetrag jeder Person abgezogen. Getränke, Preise und Freibetrag können jederzeit über die Integrationsoptionen bearbeitet werden.
Die Sensoren des Preisliste-Benutzers verwenden immer englische Entitäts-IDs mit dem Präfix `price_list`, z. B. `sensor.price_list_free_amount` oder `sensor.price_list_wasser_price`.

## Freigetränke (Optional)

Wenn in den Integrationsoptionen aktiviert, können Freigetränke separat erfasst werden.
Ein eigener Benutzer (Standardname `Freigetränke`, konfigurierbar) sammelt alle
gratis gebuchten Getränke und stellt die gleichen Zähl- und Betragssensoren wie
normale Nutzer bereit, z. B. `sensor.free_drinks_bier_count` und
`sensor.free_drinks_amount_due`. Jeder Freigetränke-Eintrag wird in einer CSV-Datei
unter `/config/backup/tally_list/free_drinks/` protokolliert. Für jedes Jahr
entsteht ein Feed-Sensor wie `sensor.free_drink_feed_2024`, der den letzten Eintrag
anzeigt und die jüngsten Freigetränke in seinen Attributen auflistet.

Die Funktion kann in den Integrationsoptionen aktiviert oder deaktiviert und der
Name des Freigetränke-Benutzers angepasst werden.

## WebSocket-API

Der WebSocket-Befehl `tally_list/get_admins` gibt alle Benutzer mit Override-Rechten zurück und kann aus dem Home-Assistant-Frontend oder einem externen Client aufgerufen werden. Der Befehl erfordert einen authentifizierten Home-Assistant-Benutzer.

```js
await this.hass.callWS({ type: "tally_list/get_admins" });
```

Beispielantwort:

```json
{"admins":["tablet_dashboard","Test","Test 2"]}
```

Der Befehl `tally_list/is_public_device` liefert zurück, ob der authentifizierte Benutzer als öffentliches Gerät konfiguriert ist:

```js
await this.hass.callWS({ type: "tally_list/is_public_device" });
```

Beispielantwort, wenn der Benutzer als öffentliches Gerät konfiguriert ist:

```json
{"is_public": true}
```

Beispielantwort für einen normalen Benutzer:

```json
{"is_public": false}
```
