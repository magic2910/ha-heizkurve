# Heizkurve für Home Assistant

Vorausschauende Heizkurve für Wärmepumpen mit Fußbodenheizung. Die Integration berechnet den Vorlauf-Sollwert aus Außentemperatur, Wettervorhersage, Raumtemperatur und PV-Prognose. Geschrieben wird der Wert von einer Automation aus dem mitgelieferten Blueprint, damit das gerätespezifische Wissen sichtbar und anpassbar bleibt.

Entstanden aus dem YAML-Paket "Heizkurve v2" für eine Rotex HPSU (ESPHome HPSU CAN). Die Rechnung ist herstellerneutral.

## Funktionen

- Lineare Heizkurve mit Steigung und Niveau, begrenzt auf Min-/Max-Vorlauf und eine feste Anlagengrenze (z. B. 25 °C bei der Rotex).
- Effektive Außentemperatur: Mischung aus Messung und Vorhersage der nächsten Stunden, wegen der Trägheit der Fußbodenheizung.
- Raumkorrektur (P-Anteil) und I-Anteil mit Anti-Windup, der nur läuft, solange die Integration aktiv ist.
- Solarabzug aus der PV-Prognose von Helios Forecast.
- Heizbedarf nach Heizgrenze mit ±0,5 K Hysterese auf dem 48-h-Mittel der Vorhersage.
- Taktsperre: erkennt taktenden Kompressor (Warmwasser ausgenommen) und gibt eine Pause vor.
- Störung: meldet, wenn der Sollwert länger als 5 Minuten ungültig ist.
- Kennzahlen: Komfortabweichung, Gradstunden, Heizgradtage, Wärme pro Tag, kWh je Heizgradtag, Starts und Laufzeit.

## Installation

1. HACS öffnen, oben rechts das Menü, "Benutzerdefinierte Repositories", `https://github.com/magic2910/ha-heizkurve` als Typ "Integration" hinzufügen.
2. "Heizkurve" installieren und Home Assistant neu starten.
3. Einstellungen, Geräte & Dienste, Integration hinzufügen, "Heizkurve".

## Einrichtung

Der Dialog hat drei Schritte. Nur die Außentemperatur ist Pflicht. Fehlt ein optionaler Eingang, entfällt nur der zugehörige Teil der Formel, und die passenden Parameter werden gar nicht erst angelegt. Alles lässt sich später unter "Konfigurieren" ändern.

Ist das YAML-Paket "Heizkurve v2" installiert, übernimmt die Einrichtung dessen Werte (`input_number.heizkurve_v2_*`) einschließlich des aktuellen I-Anteils als Startwerte.

### Unterstützte Quellen

| Eingang | Pflicht | Geeignete Quellen (Beispiele) | Ohne diesen Eingang |
| --- | --- | --- | --- |
| Außentemperatur | ja | eigene Wetterstation (z. B. Homematic IP, Ecowitt, Netatmo), jeder Temperatursensor im Freien | – |
| Außentemperatur Fallback | nein | Außenfühler der Wärmepumpe (z. B. ESPHome HPSU CAN), zweiter Sensor | Sollwert wird nicht verfügbar, wenn der Hauptfühler ausfällt |
| Raumtemperatur | nein | Thermostate oder Raumsensoren (z. B. Homematic IP, Zigbee über ZHA oder Zigbee2MQTT, tado), beliebig viele, es zählt der Mittelwert | reine Außentemperaturführung ohne Raumkorrektur und I-Anteil |
| Zieltemperatur | nein | Helfer Zahl (`input_number`), `number`- oder `sensor`-Entität | eigene Zahl-Entität "Zieltemperatur" |
| Wettervorhersage | nein | jede `weather`-Entität mit stündlicher Vorhersage, z. B. Met.no, OpenWeatherMap, DWD Weather (HACS), Weather Fusion AI; mehrere in Reihenfolge als Fallback | keine Vorhersage, effektive = gemessene Außentemperatur; Heizbedarf nach aktueller Außentemperatur |
| PV-Prognose | nein | [Helios Forecast](https://github.com/ReikanYsora/Helios-Forecast) (HACS): der Sensor "Power now" einer Anlage, z. B. `sensor.dach_pv_anlage_power_now`, mit dem Attribut `forecast` (15-Minuten-Werte in Watt) | kein Solarabzug |
| Kompressorstatus | nein | Binary-Sensor der Wärmepumpe (z. B. ESPHome HPSU CAN) | keine Taktsperre, keine Starts und Laufzeit |
| Betriebsart | nein | Sensor oder Select der Wärmepumpe mit eigenem Wert für Warmwasser | Warmwasser-Läufe zählen als Starts |
| Wärmemengenzähler | nein | Energiesensor der Wärmepumpe oder externer Wärmemengenzähler | keine Wärme pro Tag, keine kWh je Heizgradtag |
| Vergleichskurve | nein | jeder Vorlauf-Sensor, z. B. die bisherige Heizkurve | kein Differenz-Sensor |

## Die Formel

```
Vorlauf = Ziel + Steigung · (Ziel − T_eff) + Niveau + Raumfaktor · (Ziel − Raum) − Solarabzug + I-Anteil
T_eff   = (1 − Gewicht) · T_jetzt + Gewicht · Vorhersage-Mittel (begrenzt auf T_jetzt ± max. Abweichung)
```

Das Ergebnis wird auf Min- und Max-Vorlauf begrenzt; der Min-Vorlauf liegt nie unter der Anlagengrenze aus der Einrichtung.

## Entitäten

| Entität | Bedeutung |
| --- | --- |
| Vorlauf-Soll | der berechnete Sollwert; Attribute zeigen die Bestandteile |
| Heizbedarf | Heizgrenze unterschritten |
| Störung | Sollwert seit 5 min ungültig |
| Aktiv (Schalter) | Integration steuert die Wärmepumpe: I-Anteil läuft, Blueprint schreibt |
| Taktsperre (Binary-Sensor) und Taktsperre aktiv (Schalter) | Pause gegen Takten, wirkt nur zusammen mit "Aktiv" |
| Parameter (Zahlen) | Steigung, Niveau, Raumfaktor, Min-/Max-Vorlauf, Heizgrenze, Prognose-Horizont, -Gewicht, -max. Abweichung, Solar-Abzug max, PV-Referenz, I-Zeitkonstante, I max, Komfortband, Takt-Starts pro Stunde, Takt-Pause, Taktsperren max pro Tag |
| Diagnose | Außentemperatur, effektive Außentemperatur, Raumtemperatur, Prognosen, PV-Prognose, Solarabzug, I-Anteil, Kompressor heizt |
| Kennzahlen | Komfortabweichung, Gradstunden heute, Heizgradlast, Heizgradtage heute, Wärme heute, kWh je Heizgradtag, Starts in 60 min, Starts heute, Laufzeit heute, Taktsperren heute, Differenz zur Vergleichskurve |

## Blueprints

HACS installiert keine Blueprints. Importiere sie über die Knöpfe:

**Vorlauf an Wärmepumpe schreiben**
[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmagic2910%2Fha-heizkurve%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fheizkurve%2Fvorlauf_schreiben.yaml)

Schreibt stündlich den Sollwert in eine oder mehrere `number`-Entitäten, nur bei mindestens 0,2 K Änderung und nur, solange "Aktiv" an ist. Optional stellt er beim Aktivieren eine Heizkreis-Funktion (Rotex: "Fest") ein und beim Deaktivieren zurück ("Witterungsgeführt"), meldet Störungen per Notify-Aktion und überträgt den Heizbedarf als Betriebsart (Heizen/Sommer).

**Taktsperre an Wärmepumpe**
[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmagic2910%2Fha-heizkurve%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fheizkurve%2Ftaktsperre.yaml)

Setzt während einer Taktsperre ein Select auf die Sperr-Option und danach zurück, optional mit Nachricht.

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

## Umstieg vom YAML-Paket "Heizkurve v2"

1. Integration installieren und einrichten, "Aktiv" und "Taktsperre aktiv" bleiben aus. Die Integration schreibt dann nichts.
2. Als Vergleichskurve `sensor.heizkurve_v2` wählen. Die Differenz muss genau dem I-Anteil des Pakets entsprechen, weil die Integration ihren I-Anteil nur bei "Aktiv" einrechnet.
3. Zwischen zwei vollen Stunden umschalten: `automation.heizkurve_zu_rotex` sowie die Taktsperr- und Überwachungs-Automationen des Pakets deaktivieren, die Blueprint-Automationen anlegen, "Aktiv" der Integration einschalten. Den I-Anteil hat die Integration bei der Einrichtung übernommen; ist seither Zeit vergangen, vorher vergleichen.
4. Rückweg: "Aktiv" aus, Paket-Automationen wieder an.

## Entwicklung

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Die Rechenlogik liegt ohne Home-Assistant-Abhängigkeit in `custom_components/heizkurve/calc.py`.
