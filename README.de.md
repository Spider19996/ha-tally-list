# Tally List Integration

🇬🇧 [Read English version](README.md)

Diese benutzerdefinierte Integration für [Home Assistant](https://www.home-assistant.io/) wird über HACS bereitgestellt und hilft, Getränkezählungen für mehrere Personen zu verwalten. Alle Personen mit einem verknüpften Home-Assistant-Benutzerkonto werden automatisch importiert. Getränke werden einmal definiert und von allen gemeinsam genutzt.

## Funktionen

- Automatischer Import von Personen mit Benutzerkonten.
- Enthaltene Dashboard-Karten (Strichliste, Rangliste, Freigetränke, PIN) – keine separate Karten-Installation nötig.
- Gemeinsame Getränkeliste mit Namen und Preis für jede Person.
- Sensoren für Getränkezählungen, Getränkepreise, einen Freibetrag, ein persönliches Guthaben und den Gesamtbetrag pro Person.
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

Die Lovelace-Dashboard-Karten sind in der Integration enthalten – eine separate Karten-Installation ist nicht nötig. Nach dem Neustart wird die Kartendatei unter `/tally_list/tally-list-card.js` bereitgestellt und automatisch als Lovelace-Ressource registriert, sodass die Karten sofort in der Karten-Auswahl erscheinen.

### Umstieg vom separaten Karten-Repository

Falls du die Karte bisher aus dem separaten Repository `ha-tally-list-lovelace` installiert hast:

1. Diese Integration aktualisieren und Home Assistant neu starten.
2. In HACS das Repository **Tally List Card** (Lovelace) entfernen.
3. Unter **Einstellungen → Dashboards → Ressourcen** die alte `/hacsfiles/...`-Ressource löschen.

Die neue Ressource wird automatisch angelegt, bestehende Dashboard-Karten funktionieren weiter.

### YAML-Modus

Wenn deine Dashboards im YAML-Modus gespeichert sind, die Ressource manuell eintragen:

```yaml
lovelace:
  resources:
    - url: /tally_list/tally-list-card.js
      type: module
```

## Dashboard-Karten

Die Integration liefert folgende Karten mit (die Element-Namen bleiben unverändert, bestehende Dashboards funktionieren weiter):

### Tally List Card

Eine Lovelace-Karte, die Getränkezähler pro Nutzer anzeigt und aktualisieren lässt. Nach der Auswahl eines Namens erscheinen die Anzahl der Getränke sowie der fällige Betrag. Nutzer und Preise werden automatisch aus der Integration gelesen. Währung und Sprache folgen den Home-Assistant-Einstellungen (Englisch und Deutsch, manuelle Auswahl möglich).

![Screenshot der Tally List Karte](images/image1.png)

```yaml
type: custom:tally-list-card
```

Alle von der Integration erkannten Nutzer erscheinen in der Auswahlliste. Administratoren (laut Integration) können jeden Nutzer wählen, normale Nutzer nur sich selbst. Getränkepreise stammen aus Sensoren `sensor.price_list_<getränk>_price`. Falls `sensor.price_list_free_amount` existiert, wird dieser Betrag jedem Nutzer gutgeschrieben. Sensoren `sensor.<name>_amount_due` überschreiben den berechneten Betrag.

Unter der Nutzerauswahl ermöglicht eine Buttonreihe, wie viele Getränke auf einmal hinzugefügt oder entfernt werden (1, 3, 5 oder 10). Die gewählte Anzahl wird hervorgehoben und für alle folgenden Aktionen verwendet.

Ein Klick auf **+X** fügt die ausgewählte Anzahl an Getränken hinzu:

```yaml
action: tally_list.add_drink
data:
  user: Robin
  drink: Wasser
  count: 3
```

Über den Button **Getränk entfernen** werden Getränke mit `tally_list.remove_drink` abgezogen. Wird `count` weggelassen, beträgt der Standardwert `1`.

Optionen (im UI):

* **Sperrzeit (ms)** – Wie lange die Buttons nach dem Drücken deaktiviert bleiben. Standard `400`.
* **Session-Timeout (s)** – Zeit bis zum automatischen Logout nach dem Login. Standard `30`.
* **Maximale Breite (px)** – Begrenzung der Kartenbreite. Standard `500`.
* **Entfernen-Menü anzeigen** – Ein-/Ausblenden des Menüs zum Entfernen.
* **Schrittweiten-Auswahl anzeigen** – Schaltflächen zur Auswahl der Schrittweite (1, 3, 5, 10) anzeigen.
* **Nur sich selbst zeigen** – Auswahl auch für Admins auf den eingeloggten Nutzer beschränken.
* **Namen kürzen** – Namen in der Auswahl abkürzen, bei Bedarf mit weiteren Buchstaben eindeutig halten.
* **Nutzerauswahl** – Layout der Nutzerauswahl: **Liste**, **Tabs** oder **Grid**.
* **Sprache** – **Auto**, **Deutsch** oder **English** erzwingen.
* **Version** – Zeigt die installierte Version an.

### Strichliste Rangliste

Eine Karte, die alle Nutzer nach offenem Betrag sortiert auflistet.

```yaml
type: custom:tally-due-ranking-card
```

Optionen:

* **Maximale Breite (px)** – Begrenzung der Kartenbreite.
* **sort_by** – `due_desc` (Standard), `due_asc` oder `name`.
* **sort_menu** – Dropdown zur Änderung der Sortierung anzeigen.
* **show_reset** – Admin-Reset-Button anzeigen.
* **show_total** – Gesamtbetrag aller Nutzer anzeigen.
* **max_entries** – Anzahl angezeigter Nutzer begrenzen (`0` = unbegrenzt).
* **hide_free** – Nutzer ohne offenen Betrag ausblenden.
* **show_copy** – Schaltfläche **Tabelle kopieren** anzeigen.
* **shorten_user_names** – Namen in der Tabelle abkürzen.

### Strichliste Freigetränke

Bucht Freigetränke mit Pflichtkommentar. Zähler werden lokal gepuffert, bis sie abgeschickt werden. Mit dem Reset-Button lassen sich alle Zähler zurücksetzen. Vor der PIN-Eingabe muss ein Nutzer gewählt werden.

```yaml
type: custom:tally-list-free-drinks-card
```

Optionen:

* **show_prices** – Preise anzeigen (`true` standardmäßig).
* **comment_presets** – Vordefinierte Kommentarpräfixe. Jedes Element hat `label` und optional `require_comment`.
* **session_timeout_seconds** – Zeit bis zum automatischen Logout nach dem Login (`30` standardmäßig).
* **pin_lock_ms** – PIN-Sperrzeit in Millisekunden (`5000` standardmäßig).
* **free_drinks_timer_seconds** – Auto-Reset-Timer in Sekunden (`0` = aus).
* **free_drinks_per_item_limit** – Limit je Getränk (`0` = aus).
* **free_drinks_total_limit** – Gesamtlimit (`0` = aus).
* **Namen kürzen** – Namen in der Auswahl abkürzen.

Beispiel:

```yaml
type: custom:tally-list-free-drinks-card
comment_presets:
  - label: Einsatz
    require_comment: true
  - label: Übung
    require_comment: false
```

### Strichliste PIN setzen

Nutzer können ihre eigene 4-stellige PIN setzen oder zurücksetzen. Administratoren können für jeden Nutzer die PIN festlegen. Die Karte kann über den Lovelace-Karteneditor hinzugefügt werden. Beim Öffnen der Karte kann ein konfigurierbarer Hinweis anzeigen, keine wichtige PIN (z. B. die der Bankkarte) zu verwenden. Wird der Text leer gelassen, wird kein Hinweis gezeigt.

```yaml
type: custom:tally-set-pin-card
```

Die Karte verwendet die gleiche Benutzerliste wie die Hauptkarte und benötigt normalerweise keine zusätzliche Konfiguration.

Optionen:

* **Sperrzeit (ms)** – Wartezeit nach jeder PIN-Eingabe (auch bei Fehlern) (`5000` Standard).
* **user_selector** – Layout der Nutzerauswahl: `list`, `tabs` oder `grid` (`list` standardmäßig).
* **Namen kürzen** – Namen in der Auswahl abkürzen.
* **pin_warning** – Warntext beim Öffnen der Karte. Unterstützt Zeilenumbrüche und einfache Markdown-Formatierung für _kursiv_, **fett** und __unterstrichen__. Leerer Text blendet den Hinweis aus.

Zum Speichern der neuen PIN wird der Service `tally_list.set_pin` aufgerufen, z. B.:

```yaml
action: tally_list.set_pin
data:
  user: Erika Mustermann
  pin: "1234"
```

## Verwendung

Beim ersten Einrichten wirst du nach verfügbaren Getränken gefragt. Alle Personen mit Benutzerkonto teilen sich diese Liste. Getränke und Preise können später über die Integrationsoptionen verwaltet werden.

### Dienste

- `tally_list.add_drink`: erhöht die Anzahl eines Getränks für eine Person (schlägt fehl, wenn die Person nicht existiert; Anzahl kann angegeben werden).
- `tally_list.remove_drink`: verringert die Anzahl eines Getränks für eine Person (nie unter null; Anzahl kann angegeben werden).
- `tally_list.set_drink`: setzt die Anzahl eines Getränks auf einen bestimmten Wert.
- `tally_list.reset_counters`: setzt alle Zähler für eine Person oder – ohne Angabe einer Person – für alle zurück.
- `tally_list.export_csv`: exportiert alle `_amount_due`-Sensoren als CSV-Dateien (`daily`, `weekly`, `monthly` oder `manual`), gespeichert unter `/config/tally_list/<type>/`.
- `tally_list.set_pin`: setzt oder entfernt eine persönliche vierstellige PIN aus Ziffern für öffentliche Geräte (Admins können PINs für andere Nutzer setzen).
- `tally_list.add_credit`: erhöht das Guthaben einer Person.
- `tally_list.remove_credit`: verringert das Guthaben einer Person.
- `tally_list.set_credit`: setzt das Guthaben einer Person auf einen exakten Betrag.

### Reset-Schalter

Jede Person erhält eine Entität `button.<person>_reset_tally`, um ihre Zähler zurückzusetzen. Nur Tally Admins dürfen sie betätigen.

### Guthaben

Jede Person verfügt außerdem über eine Entität `sensor.<person>_credit`, die ihr verfügbares Guthaben speichert. Positives Guthaben verringert den `*_amount_due`-Sensor, negatives erhöht ihn. Das Guthaben wird über die Dienste `tally_list.add_credit`, `tally_list.remove_credit` und `tally_list.set_credit` angepasst.

## Preisliste und Sensoren

Alle Getränke werden in einer gemeinsamen Preisliste gespeichert. Ein spezieller Benutzer namens `Preisliste` (englisch `Price list`) stellt für jedes Getränk einen Preissensor sowie einen Sensor für den Freibetrag bereit, während normale Personen Zähl-, Guthaben- und Gesamtbetragssensoren erhalten. Freibetrag und persönliches Guthaben werden vom Gesamtbetrag jeder Person abgezogen. Getränke, Preise und Freibetrag können jederzeit über die Integrationsoptionen bearbeitet werden.
Die Sensoren des Preisliste-Benutzers verwenden immer englische Entitäts-IDs mit dem Präfix `price_list`, z. B. `sensor.price_list_free_amount` oder `sensor.price_list_wasser_price`.

Jede Änderung an der Preisliste wird in jährlichen CSV-Dateien unter `/config/tally_list/price_list/` protokolliert. Ein Feed-Sensor `sensor.price_list_feed` zeigt den letzten Eintrag an und stellt die jüngsten Änderungen in seinen Attributen bereit.

## Freigetränke (Optional)

Wenn in den Integrationsoptionen aktiviert, können Freigetränke separat erfasst werden.
Ein eigener Benutzer (Standardname `Freigetränke`, konfigurierbar) sammelt alle
gratis gebuchten Getränke und stellt die gleichen Zähl- und Betragssensoren wie
normale Nutzer bereit, z. B. `sensor.free_drinks_bier_count` und
`sensor.free_drinks_amount_due`. Jeder Freigetränke-Eintrag wird in einer
jährlichen CSV-Datei `free_drinks_<Jahr>.csv` unter
`/config/tally_list/free_drinks/` protokolliert. Ein Feed-Sensor
`sensor.free_drink_feed` zeigt den letzten Eintrag an und listet die jüngsten
Freigetränke in seinen Attributen auf.

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

Öffentliche Geräte können einen Benutzer einmalig über den Befehl `tally_list/login` authentifizieren, damit nachfolgende Dienstaufrufe keinen `pin`-Parameter mehr benötigen:

```js
await this.hass.callWS({ type: "tally_list/login", user: "Alice", pin: "1234" });
```

Beispielantwort bei Erfolg:

```json
{"success": true}
```

Zum Beenden der Sitzung `tally_list/logout` aufrufen:

```js
await this.hass.callWS({ type: "tally_list/logout" });
```
