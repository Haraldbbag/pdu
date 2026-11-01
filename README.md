# Intellinet IP PDU für Home Assistant

Custom Integration für die 8-fach-Steckdosenleisten „IP PDU“ (Intellinet 163682 bzw. baugleich, Firmware 1.0.7).
Die Leisten haben keine offizielle API. Die Integration nutzt die Webseiten der Leiste:

| Zweck | Aufruf | Passwort |
|---|---|---|
| Status lesen | `GET /status.xml` | nein |
| Login prüfen, Firmware/Name lesen | `GET /info_system.htm` | ja (Basic Auth) |
| Schalten | `GET /control_outlet.htm?outlet0=1&outlet3=1&op=0` (`op` 0 = an, 1 = aus) | ja |

## Was angelegt wird (pro Leiste ein Gerät)

- 8 Schalter (eine pro Dose)
- Sensoren: Strom (A), Temperatur, Luftfeuchte, Status
- Diagnose: „Erreichbar“ (aus, wenn die Leiste nicht antwortet; die Dosen sind dann „nicht verfügbar“)
- Aktion `intellinet_pdu.set_outlets`: mehrere Dosen einer Leiste in **einem** Aufruf schalten, damit die in der Leiste eingestellte Ein-/Ausschaltverzögerung greift

Nicht vorhanden (bewusst): „Alle an/aus“ und Neustart pro Dose. Welche Dosen ein Kino schaltet, regelt eine Szene.

## Installation

1. HACS → Benutzerdefinierte Repositories → `https://github.com/Haraldbbag/pdu`, Typ „Integration“.
2. „Intellinet IP PDU“ installieren, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → „Intellinet IP PDU“. Pro Leiste einmal.

### Felder bei der Einrichtung

| Feld | Beispiel | Bedeutung |
|---|---|---|
| IP-Adresse | `10.49.55.51` | |
| Benutzername / Passwort | `admin` / `admin` (vorausgefüllt) | Werkslogin der Leisten |
| Name | `PDU M1-1` | leer = Systemname aus der Leiste |
| Kürzel für Entity-IDs | `m1` | ergibt `switch.pdu_m1_01` … Damit bleiben alte IDs erhalten |
| Nummer der ersten Dose | `1` oder `9` | zweite Leiste eines Kinos beginnt bei 9 → `switch.pdu_m1_09…16` |

Die alten YAML-Schalter mit denselben IDs müssen **vorher** entfernt sein, sonst hängt HA `_2` an.

## Dosen benennen

Gerät → Integration „Intellinet IP PDU“ → Leiste → **Konfigurieren**: pro Dose ein Name (z. B. „Projektor“).
Leer = „Out 1“ … „Out 8“ (bzw. ab der ersten Dosennummer). Die Entity-IDs ändern sich dabei nicht. Hier lässt sich auch das Abfrageintervall einstellen (Standard 5 s).

## Hinweise

- Die Leiste schaltet mit der eigenen Verzögerung (Configuration → PDU, 0–7 s je Dose). Der Schalter zeigt den neuen Zustand sofort an und gleicht sich danach mit der Leiste ab.
- Anfragen an eine Leiste laufen nacheinander, nie parallel.
- Im Web-Interface der Leiste sind auf der Seite „Socket“ die Häkchen für Dose 2–8 vorausgewählt. Dort nie blind „Apply“ drücken.
