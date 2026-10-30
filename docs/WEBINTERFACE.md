# Webinterface für den Fernzugriff – Idee (I-004)

Stand: **Idee** (30.10.2026), noch nicht programmiert.

Ziel: Von remote (Browser auf PC, Tablet, Handy) auf das Tool zugreifen – mit der Geräteübersicht und den
Gerätereitern. Nur ausgewählte Geräte sind im Webinterface sichtbar.

## Wie es funktionieren würde

- Das Tool startet einen kleinen **HTTPS-Webserver** (z. B. `https://recoverypc:8443`) im selben Programm – gleiche
  Daten, immer aktuell; das Tool muss dafür laufen.
- Ansichten:
  - **Geräteübersicht:** Status, grüne/rote Balken, Auto-Status (wie links im Tool).
  - **Geräteseite** mit den Reitern: Aufträge (mit Log), Übersicht, Disks, Images, Backups, Netzwerk,
    Automatisierung, Verlauf.
- **Pro Gerät freigeben:** im Gerätefenster, Reiter „Netzwerk“, Schalter **„Im Webinterface sichtbar“** (Standard aus).

## Anschauen oder steuern (offen)

- **Nur anschauen:** Status, Fortschritt, Logs, Verlauf – einfacher und sicherer.
- **Mit Aktionen:** z. B. Wake-on-LAN, Automatisierung ein/aus, Pausieren (Stopp-Knopf), Herunterfahren/Neustart,
  Disk-Image erstellen. Löschende Aktionen (Zurückspielen, OS installieren) nur mit doppelter Bestätigung oder gar nicht.

## Sicherheit

- Anmeldung mit Benutzer und Passwort (nur als Hash gespeichert), Sperre nach Fehlversuchen.
- HTTPS mit eigenem Zertifikat des Tools.
- **Nicht direkt ins Internet** – von unterwegs über VPN (WireGuard der Firewall/des Routers oder Tailscale).
- Protokoll: wer was von wo gemacht hat, im Verlauf des Geräts.
- Datenschutz (DSG): Inventar enthält Seriennummern und Benutzernamen; **Windows-Schlüssel im Webinterface nicht
  anzeigen**.

## Alternative ohne Programmierung

Fernzugriff auf den Desktop des Servers per VNC/xrdp über VPN – sofort möglich, aber voller Zugriff und auf dem
Handy umständlich.

## Aufwand

Nur anschauen: mittel. Mit Aktionen und mehreren Benutzern: eher gross.

## Offene Fragen

1. Nur anschauen oder auch Aktionen – welche?
2. Ein Benutzer oder mehrere (Rechte, z. B. „nur lesen“)?
3. Zugriff nur im LAN oder von unterwegs per VPN?
