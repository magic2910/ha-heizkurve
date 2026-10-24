# Heizkurve für Home Assistant

Vorausschauende Heizkurve für Wärmepumpen mit Fußbodenheizung. Die Integration berechnet den Vorlauf-Sollwert aus Außentemperatur, Wettervorhersage, Raumtemperatur und PV-Prognose. Geschrieben wird der Wert von einer Automation aus dem mitgelieferten Blueprint, damit das gerätespezifische Wissen sichtbar und anpassbar bleibt. Die Rechnung ist herstellerneutral; ein ausgearbeitetes Beispiel gibt es für die Rotex HPSU.

## Funktionen

- Lineare Heizkurve mit Steigung und Niveau, begrenzt auf Min-/Max-Vorlauf und eine feste Anlagengrenze (z. B. 25 °C bei der Rotex).
- Effektive Außentemperatur: Mischung aus Messung und Vorhersage der nächsten Stunden, wegen der Trägheit der Fußbodenheizung.
- Raumkorrektur (P-Anteil) und I-Anteil mit Anti-Windup, der nur läuft, solange die Regelung aktiv ist.
- Solarabzug aus der PV-Prognose von Helios Forecast.
- Heizbedarf nach Heizgrenze mit ±0,5 K Hysterese auf dem 48-h-Mittel der Vorhersage.
- Taktsperre: erkennt taktenden Kompressor (Warmwasser ausgenommen) und gibt eine Pause vor.
- Störung: meldet, wenn der Sollwert länger als 5 Minuten ungültig ist.
- Kennzahlen: Komfortabweichung, Gradstunden, Heizgradtage, Wärme pro Tag, kWh je Heizgradtag, Starts und Laufzeit.

## Installation

[![HACS-Repository öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=magic2910&repository=ha-heizkurve&category=integration)

1. Den Knopf oben anklicken. Er öffnet HACS in deinem Home Assistant und fügt das Repository hinzu. Ohne Knopf: HACS öffnen, oben rechts das Menü, "Benutzerdefinierte Repositories", `https://github.com/magic2910/ha-heizkurve` als Typ "Integration" hinzufügen.
2. "Heizkurve" herunterladen und Home Assistant neu starten.
3. Integration einrichten:

   [![Integration einrichten](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=heizkurve)

   Oder: Einstellungen, Geräte & Dienste, Integration hinzufügen, "Heizkurve". Taucht sie dort nicht auf, die Seite im Browser hart neu laden (Cache).

### Updates

Neue Versionen erscheinen als [GitHub-Release](https://github.com/magic2910/ha-heizkurve/releases). HACS meldet sie in Home Assistant unter Einstellungen, Updates; installiert wird erst, wenn du dort auf "Aktualisieren" klickst, danach Home Assistant neu starten. Die Release-Notizen zeigen, was sich geändert hat.

Blueprints aktualisiert HACS nicht. Hat sich ein Blueprint geändert (steht in den Release-Notizen), unter Einstellungen, Automationen & Szenen, Blueprints beim Blueprint über das Menü "Blueprint erneut importieren" wählen.

## Einrichtung

Der Dialog hat drei Schritte. Nur die Außentemperatur ist Pflicht. Fehlt ein optionaler Eingang, entfällt nur der zugehörige Teil der Formel, und die passenden Parameter werden gar nicht erst angelegt. Alles lässt sich später unter "Konfigurieren" ändern.

### Unterstützte Quellen

| Eingang | Pflicht | Geeignete Quellen (Beispiele) | Ohne diesen Eingang |
| --- | --- | --- | --- |
| Außentemperatur | ja | eigene Wetterstation (z. B. Homematic IP, Ecowitt, Netatmo), jeder Temperatursensor im Freien | – |
| Außentemperatur Fallback | nein | Außenfühler der Wärmepumpe, zweiter Sensor | Sollwert wird nicht verfügbar, wenn der Hauptfühler ausfällt |
| Raumtemperatur | nein | Thermostate oder Raumsensoren, beliebig viele, es zählt der Mittelwert | reine Außentemperaturführung ohne Raumkorrektur und I-Anteil |
| Zieltemperatur | nein | Helfer Zahl (`input_number`), `number`- oder `sensor`-Entität | eigene Zahl-Entität "Zieltemperatur" |
| Wettervorhersage | nein | jede `weather`-Entität mit stündlicher Vorhersage; mehrere in Reihenfolge als Fallback | keine Vorhersage, effektive = gemessene Außentemperatur; Heizbedarf nach aktueller Außentemperatur |
| PV-Prognose | nein | Helios Forecast: der Sensor "Power now" einer Anlage, z. B. `sensor.dach_pv_anlage_power_now` (Attribut `forecast` mit 15-Minuten-Werten in Watt) | kein Solarabzug |
| Kompressorstatus | nein | Binary-Sensor der Wärmepumpe | keine Taktsperre, keine Starts und Laufzeit |
| Betriebsart | nein | Sensor oder Select der Wärmepumpe mit eigenem Wert für Warmwasser | Warmwasser-Läufe zählen als Starts |
| Wärmemengenzähler | nein | Energiesensor der Wärmepumpe oder externer Wärmemengenzähler | keine Wärme pro Tag, keine kWh je Heizgradtag |
| Vergleichskurve | nein | jeder Vorlauf-Sensor, z. B. die Kurve der Wärmepumpe selbst | kein Differenz-Sensor |

## Empfohlene Integrationen

Keine davon ist Pflicht. Je mehr Eingänge belegt sind, desto genauer und vorausschauender wird die Kurve.

| Zweck | Integration | Hinweis |
| --- | --- | --- |
| PV-Prognose für den Solarabzug | [Helios Forecast](https://github.com/ReikanYsora/Helios-Forecast) (HACS) | selbstlernende Prognose für die eigene Anlage, liefert 15-Minuten-Werte für 7 Tage |
| Wettervorhersage | [Met.no](https://www.home-assistant.io/integrations/met/) (in HA enthalten) | kostenlos, ohne Konto, guter Start |
| Wettervorhersage | [Deutscher Wetterdienst](https://github.com/FL550/dwd_weather) (HACS) | MOSMIX-Stationsvorhersage, in Deutschland oft genauer |
| Wettervorhersage | [Weather Fusion AI](https://github.com/Zara-Toorox/weather-fusion-ai) (HACS) | mischt mehrere Quellen und lernt dazu; als erste Wahl, Met.no oder DWD als Fallback dahinter |
| Wettervorhersage | [OpenWeatherMap](https://www.home-assistant.io/integrations/openweathermap/) (in HA enthalten) | braucht einen kostenlosen API-Schlüssel |
| Außentemperatur | [Homematic(IP) Local](https://github.com/SukramJ/homematicip_local) (HACS), [Ecowitt](https://www.home-assistant.io/integrations/ecowitt/), [Netatmo](https://www.home-assistant.io/integrations/netatmo/) | eine eigene Wetterstation im Schatten ist genauer als der Außenfühler der Wärmepumpe |
| Raumtemperatur | [Homematic(IP) Local](https://github.com/SukramJ/homematicip_local) (HACS), [ZHA](https://www.home-assistant.io/integrations/zha/), [Zigbee2MQTT](https://www.zigbee2mqtt.io/), [tado](https://www.home-assistant.io/integrations/tado/) | mehrere Räume eintragen; Räume mit Kamin oder starker Sonne besser weglassen |
| Anbindung der Wärmepumpe | [ESPHome](https://www.home-assistant.io/integrations/esphome/), z. B. mit einer HPSU-CAN-Firmware für Rotex/Daikin | liefert Kompressorstatus, Betriebsart, Wärmemenge und die `number`-Entitäten, in die der Blueprint schreibt |

## Die Formel

```
Vorlauf = Ziel + Steigung · (Ziel − T_eff) + Niveau + Raumfaktor · (Ziel − Raum) − Solarabzug + I-Anteil
T_eff   = (1 − Gewicht) · T_jetzt + Gewicht · Vorhersage-Mittel (begrenzt auf T_jetzt ± max. Abweichung)
```

Das Ergebnis wird auf Min- und Max-Vorlauf begrenzt; der Min-Vorlauf liegt nie unter der Anlagengrenze aus der Einrichtung.

## Steuerung

Die Integration rechnet immer, auch wenn alles aus ist. Was sie an der Wärmepumpe bewirkt, entscheiden zwei Schalter:

| Schalter | Aus | An |
| --- | --- | --- |
| Aktiv | Schattenbetrieb: Sollwert und Kennzahlen laufen mit, der I-Anteil lernt nicht und ist 0, der Blueprint schreibt nichts und stellt die Heizkreis-Funktion zurück | Regelung: der Blueprint schreibt den Sollwert, der I-Anteil lernt und wird eingerechnet. Beim Ausschalten wird der I-Anteil auf 0 gesetzt. |
| Taktsperre aktiv | keine Taktsperre, der Binary-Sensor "Taktsperre" bleibt aus | bei zu vielen Starts schaltet der Binary-Sensor für die Takt-Pause an; der Taktsperre-Blueprint setzt dann die Wärmepumpe auf Pause. Wirkt nur zusammen mit "Aktiv". |

Warum Schalter in der Integration und nicht nur im Blueprint: Die Integration muss wissen, ob ihr Sollwert tatsächlich an der Wärmepumpe ankommt. Nur dann darf der I-Anteil lernen, sonst würde er gegen eine Wärmepumpe "anregeln", die gar nicht zuhört, und bis zur Grenze hochlaufen. Ebenso darf eine Taktsperre nur gezählt werden und den I-Anteil anhalten, wenn sie wirklich ausgeführt wird. Ob eine Automation an ist, kann die Integration nicht zuverlässig sehen; die Schalter sind deshalb die eine Stelle, an der man die Regelung ein- und ausschaltet. Die Automationen selbst bleiben dauerhaft an.

"Zieltemperatur" erscheint nur, wenn bei der Einrichtung keine eigene Entität für die Zieltemperatur gewählt wurde.

## Konfiguration

Alle Parameter sind Zahl-Entitäten am Gerät "Heizkurve" und wirken sofort. Parameter, deren Eingang fehlt, werden nicht angelegt.

### Heizkurve

| Parameter | Standard | Wirkung |
| --- | --- | --- |
| Steigung | 0,30 | Wie stark der Vorlauf steigt, wenn es draußen kälter wird: pro Kelvin Abstand zwischen Ziel- und Außentemperatur. Wirkt vor allem an kalten Tagen. Fußbodenheizung typisch 0,2–0,5, Heizkörper 0,8–1,5. |
| Niveau | −0,5 K | Parallelverschiebung der ganzen Kurve. Wirkt an allen Tagen gleich, fällt aber an milden Tagen am meisten auf. |
| Min-Vorlauf | 25 °C | Untergrenze; nie unter der Anlagengrenze aus der Einrichtung. |
| Max-Vorlauf | 35 °C | Obergrenze, schützt Estrich und Bodenbelag. Fußbodenheizung meist 35–40 °C. |
| Heizgrenze | 16 °C | Oberhalb dieser Temperatur (48-h-Mittel der Vorhersage, ±0,5 K Hysterese) meldet "Heizbedarf" aus. |

### Raum

| Parameter | Standard | Wirkung |
| --- | --- | --- |
| Raumfaktor | 1,0 | Sofortkorrektur: pro Kelvin, das der Raum unter dem Ziel liegt, so viele Kelvin mehr Vorlauf. 0 schaltet die Raumkorrektur ab. Träge Fußbodenheizung 0,5–1,5; zu hoch führt zu Pendeln. |
| I-Zeitkonstante | 24 h | Wie schnell der I-Anteil bleibende Abweichungen ausgleicht: bei 1 K zu kalt wächst er um 1 K pro Zeitkonstante. Kleiner = schneller, aber unruhiger. 0 schaltet ihn ab. |
| I max | 2 K | Begrenzung des I-Anteils in beide Richtungen. |
| Komfortband | 0,5 K | Abweichung vom Ziel, die noch als "komfortabel" gilt; Grundlage für Komfortabweichung und Taktsperre. |

### Prognose

| Parameter | Standard | Wirkung |
| --- | --- | --- |
| Prognose-Horizont | 8 h | Wie weit Wetter- und PV-Vorhersage vorausgeschaut werden. Etwa die Trägheit des Hauses: Fußbodenheizung im Estrich 6–12 h. |
| Prognose-Gewicht | 0,5 | Anteil der Vorhersage an der effektiven Außentemperatur. 0 = nur Messung, 1 = nur Vorhersage. |
| Prognose max. Abweichung | 5 K | Wie weit die Vorhersage die Messung höchstens verschieben darf; schützt vor Ausreißern. |
| Solar-Abzug max | 1 K | Höchster Vorlaufabzug, wenn viel Sonne erwartet wird. |
| PV-Referenz | 20 kWh | PV-Ertrag im Prognose-Horizont, bei dem der volle Abzug greift; darunter anteilig. Etwa der Ertrag eines sonnigen Wintertags im Horizont. |

### Taktsperre

| Parameter | Standard | Wirkung |
| --- | --- | --- |
| Takt-Starts pro Stunde | 3 | So viele Kompressorstarts in 60 Minuten lösen eine Sperre aus. |
| Takt-Pause | 60 min | Dauer der Sperre. Sie endet früher, wenn der Raum mehr als 0,5 K unter das Komfortband fällt. |
| Taktsperren max pro Tag | 4 | Danach keine weitere Sperre bis Mitternacht. |

### Werte ermitteln

**Startwerte.** Steigung und Niveau der bisherigen Wärmepumpen-Kurve sind ein guter Anfang, wenn die Formel ähnlich ist. Sonst mit Steigung 0,3 und Niveau 0 bei Fußbodenheizung beginnen, Raumfaktor 1, I-Anteil zunächst aus (I-Zeitkonstante 0).

**Von Hand einstellen.** Immer nur einen Wert ändern und mindestens einen Tag beobachten, die Fußbodenheizung ist träge.

- An milden Tagen (5–12 °C) zu kalt oder zu warm: Niveau in Schritten von 0,5 K anpassen.
- Nur an kalten Tagen (unter 0 °C) zu kalt oder zu warm: Steigung in Schritten von 0,05 anpassen.
- Raum schwingt (abwechselnd zu warm und zu kalt): Raumfaktor verkleinern.
- Ist die Kurve gut eingestellt, den I-Anteil mit 24 h einschalten. Er gleicht dann Reste aus. Läuft er dauerhaft an seine Grenze, stimmt Niveau oder Steigung noch nicht: den Wert des I-Anteils ins Niveau übernehmen und den I-Anteil zurücksetzen.

**Aus den eigenen Daten.** Home Assistant speichert Langzeitstatistiken. Mit Tagesmitteln aus einer Heizperiode für Vorlauf, Raum- und Außentemperatur lässt sich die Kurve per Regression bestimmen:

```
Vorlauf − Raum = Steigung · (Raum − Außen) + Niveau
```

Die Steigung ist die Steigung der Ausgleichsgeraden, das Niveau ihr Achsenabschnitt. Nur Tage mit Heizbetrieb und ohne lange Abwesenheit verwenden.

**Mit KI.** Ein KI-Assistent kann diese Auswertung übernehmen. Zwei Wege:

- Statistiken exportieren (Verlauf, Zeitraum wählen, "Herunterladen" als CSV) und mit der Frage an die KI geben, Steigung und Niveau für obige Formel zu schätzen und Ausreißer zu nennen.
- Direkter: einen KI-Assistenten mit Zugriff auf Home Assistant nutzen, z. B. Claude über einen [Home-Assistant-MCP-Server](https://github.com/homeassistant-ai/ha-mcp). Er kann die Langzeitstatistiken selbst lesen, die Regression rechnen und Vorschläge machen. Änderungen an den Parametern sollte man trotzdem selbst bestätigen.

Gute Fragen an die KI: "Wie gut passt meine Heizkurve zu den letzten 30 Tagen?", "Ab welcher Außentemperatur hat meine Wärmepumpe tatsächlich geheizt?" (Heizgrenze), "Wie lange dauert es, bis eine Vorlaufänderung im Raum ankommt?" (Prognose-Horizont, I-Zeitkonstante).

## Entitäten

| Entität | Bedeutung |
| --- | --- |
| Vorlauf-Soll | der berechnete Sollwert; Attribute zeigen die Bestandteile |
| Heizbedarf | Heizgrenze unterschritten |
| Störung | Sollwert seit 5 min ungültig |
| Aktiv, Taktsperre aktiv (Schalter) | siehe [Steuerung](#steuerung) |
| Taktsperre (Binary-Sensor) | Pause gegen Takten läuft |
| I-Anteil zurücksetzen (Taste) | setzt den gelernten I-Anteil auf 0 |
| Parameter (Zahlen) | siehe [Konfiguration](#konfiguration) |
| Diagnose | Außentemperatur, effektive Außentemperatur, Raumtemperatur, Prognosen, PV-Prognose, Solarabzug, I-Anteil, Kompressor heizt |
| Kennzahlen | Komfortabweichung, Gradstunden heute, Heizgradlast, Heizgradtage heute, Wärme heute, kWh je Heizgradtag, Starts in 60 min, Starts heute, Laufzeit heute, Taktsperren heute, Differenz zur Vergleichskurve |

## Blueprints

HACS installiert keine Blueprints. Importiere sie über die Knöpfe. Öffnet sich danach in Home Assistant nur die Blueprint-Liste ohne Import-Dialog (Fehler im Home-Assistant-Frontend um Version 2026.10, [frontend#55080](https://github.com/home-assistant/frontend/issues/55080)), importiere von Hand: Einstellungen, Automationen & Szenen, Blueprints, "Blueprint importieren", die Adresse einfügen, "Vorschau", "Blueprint importieren".

- `https://github.com/magic2910/ha-heizkurve/blob/main/blueprints/automation/heizkurve/vorlauf_schreiben.yaml`
- `https://github.com/magic2910/ha-heizkurve/blob/main/blueprints/automation/heizkurve/taktsperre.yaml`

**Vorlauf an Wärmepumpe schreiben**
[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmagic2910%2Fha-heizkurve%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fheizkurve%2Fvorlauf_schreiben.yaml)

Schreibt stündlich den Sollwert in eine oder mehrere `number`-Entitäten, nur solange "Aktiv" an ist und nur, wenn der Wert der Wärmepumpe um mindestens 0,3 K abweicht (einstellbar, 0,1 K schreibt jede darstellbare Änderung). Jede Sollwert-Entität wird einzeln verglichen, unveränderte Werte werden nicht erneut geschrieben; das schont den CAN-Bus der Wärmepumpe. Die Heizkreis-Funktion wird nur gesetzt, wenn sie nicht schon stimmt. Ist eine Entität der Wärmepumpe nicht verfügbar (z. B. bei einem ESPHome-Verbindungsabbruch), schreibt der Blueprint in diesem Durchlauf nichts. Optional stellt er beim Aktivieren eine Heizkreis-Funktion (Rotex: "Fest") ein und beim Deaktivieren zurück ("Witterungsgeführt"), meldet Störungen per Notify-Aktion und überträgt den Heizbedarf als Betriebsart (Heizen/Sommer).

**Taktsperre an Wärmepumpe**
[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmagic2910%2Fha-heizkurve%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fheizkurve%2Ftaktsperre.yaml)

Setzt während einer Taktsperre ein Select auf die Sperr-Option und danach zurück, optional mit Nachricht.

### Inbetriebnahme

1. Integration einrichten, "Aktiv" und "Taktsperre aktiv" aus lassen. Ein paar Tage im Schattenbetrieb beobachten, optional mit der bisherigen Kurve der Wärmepumpe als Vergleichskurve.
2. Automationen aus den Blueprints anlegen.
3. "Aktiv" einschalten. Zur nächsten vollen Stunde schreibt der Blueprint den ersten Wert.
4. Läuft die Regelung stabil, bei Bedarf "Taktsperre aktiv" einschalten.
5. Zurück zur Kurve der Wärmepumpe: "Aktiv" aus.

### Beispiel Rotex HPSU (ESPHome HPSU CAN)

| Blueprint-Eingang | Entität |
| --- | --- |
| Sollwert-Entitäten | `number.hpsu_can_t_vorlauf_tag`, `number.hpsu_can_t_vorlauf_nacht` |
| Select der Heizkreis-Funktion | `select.hpsu_can_hk_funktion` (Fest / Witterungsgeführt) |
| Select an der Wärmepumpe (Taktsperre) | `select.hpsu_can_raum_thermostat` (An / Aus) |
| Select der Betriebsart (Heizgrenze) | `select.hpsu_can_betriebsmodus` (Heizen / Sommer) |

Hinweise zur Rotex:

- `select.hpsu_can_raum_thermostat` auf "An" bedeutet ohne Kontakt an J16 laut RoCon-Anleitung "keine Wärmeanforderung": Der Heizkreis pausiert, Warmwasser ist nicht betroffen.
- Die Rotex hat eine eigene Heizgrenze (`select.hpsu_can_heizgrenze_tag` / `_nacht`), gemessen am eigenen Außenfühler. Der kann in der Sonne mehrere Kelvin zu warm messen und schaltet dann die Heizung ab, obwohl die Heizkurve noch Heizbedarf meldet. Entweder die Heizgrenze der Rotex höher setzen, oder sie ausschalten und im Blueprint "Heizgrenze übernehmen" nutzen. Vorher prüfen, dass Warmwasser im Sommerbetrieb weiterläuft.
- Häufiges Schreiben über CAN sollte man vermeiden; deshalb schreibt der Blueprint nur bei Änderung.

## Entwicklung

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Die Rechenlogik liegt ohne Home-Assistant-Abhängigkeit in `custom_components/heizkurve/calc.py`.

Release: `version` in `custom_components/heizkurve/manifest.json` erhöhen und committen, dann auf GitHub unter Actions den Workflow "Release" mit "Run workflow" starten (alternativ einen Tag `v<version>` pushen). Der Workflow lässt die Tests laufen, legt Tag und GitHub-Release mit automatisch erzeugten Notizen an und bricht ab, wenn es die Version schon gibt.
