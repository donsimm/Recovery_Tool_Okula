# Windows-Master-Image mit Sysprep

Ziel: ein Windows-Image für viele Geräte. Beim Zurückspielen passt das Tool es pro Gerät an (Gerätename, Windows-Key,
Benutzer, Region Schweiz), ohne Klicks am Gerät.

Stand: **umgesetzt** (29.10.2026). Details in [TECHNIK.md](TECHNIK.md), Bedienung in der Hilfe (F1); Prüfungen am realen System: [TESTS.md](TESTS.md).

## Master-Image erstellen

1. **Referenzgerät aufsetzen**
   - Windows frisch installieren (typisches Gerät oder VM), Edition passend zu den Lizenzen (meist Pro).
   - Beim ersten Einrichtungsbildschirm (Region) **Ctrl+Shift+F3** → Neustart in den **Audit-Modus**
     (eingebauter Administrator, kein Benutzer wird angelegt).
   - Keine Domäne, kein Azure AD/Intune, kein Microsoft-Konto.
2. **Im Audit-Modus einrichten**
   - Updates, Treiber, Programme, Einstellungen. Neustarts bleiben im Audit-Modus; das Sysprep-Fenster nach dem
     Start schliessen.
   - Office mit dem Office Deployment Tool (ODT) installieren, **nicht aktivieren**.
3. **Vor Sysprep prüfen**
   - BitLocker aus (Windows 11 24H2 verschlüsselt oft automatisch): `manage-bde -status`, `manage-bde -off C:`
   - Store-Apps: nur für den Admin aktualisierte Apps lassen Sysprep abbrechen („package installed for a user but not
     provisioned“). Während der Einrichtung offline bleiben bzw. Store-Updates aus; sonst
     `Get-AppxPackage -Name <Paket> | Remove-AppxPackage`.
   - Fehlerprotokoll: `C:\Windows\System32\Sysprep\Panther\setuperr.log`
4. **Sysprep** (als Administrator):
   ```
   C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown
   ```
   `/generalize` entfernt SID, Computername und Aktivierung; `/oobe` startet beim nächsten Start die Ersteinrichtung.
   Optional `CopyProfile=true` in einer Antwortdatei: Admin-Einstellungen werden Standard für neue Benutzer.
5. **Image erstellen – Windows nicht mehr starten!**
   Direkt mit dem Okula Agent-Stick starten → „Disk-Image erstellen“, Name z. B. `Master-Win11-25H2-2026-10`.
6. **Master aktualisieren**
   Image auf das Referenzgerät zurückspielen → startet in die Ersteinrichtung → **Ctrl+Shift+F3** → aktualisieren →
   erneut Sysprep → neues Image.

**Hinweise**
- Ein Image passt für verschiedene Hardware; Treiber sucht Windows beim ersten Start (oder vorher im Audit-Modus
  installieren).
- Image von einem UEFI/GPT-Gerät läuft nur auf UEFI-Geräten.

Quelle: Microsoft Learn – „Sysprep (Generalize) a Windows installation“, „Boot Windows to Audit Mode or OOBE“.

## Funktion im Tool (umgesetzt)

Im Dialog **„Image zurückspielen“** ein Bereich *„Nach dem Zurückspielen anpassen“*:

- ☑ Gerätename aus dem Tool übernehmen
- ☑ Windows-Key setzen (OEM aus dem BIOS oder pro Gerät hinterlegt)
- ☐ Benutzer und Region Schweiz (de-CH, Tastatur Schweiz, Zeitzone Zürich)

Ablauf (Idee):
1. Image wie heute zurückspielen.
2. Agent hängt die Windows-Partition ein und erkennt ein Master-Image an
   `Windows\Setup\State\State.ini` → `ImageState=IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE`.
3. Agent legt `Windows\Panther\unattend.xml` ab (Bausteine aus `winunattend.py` der Direktinstallation):
   Computername, Product Key, lokales Konto, Region, OOBE ohne Fragen.
4. Neustart → Windows richtet sich mit diesen Angaben ein.

Lizenz: OEM-Key im BIOS und digitale Lizenz aktivieren sich bei gleicher Edition von selbst; Retail-/OEM-Keys sind
an ein Gerät gebunden, also pro Gerät hinterlegen, nicht pro Image.

Linux/Clonezilla später ähnlich: `/etc/hostname` und `/etc/hosts` nach dem Zurückspielen anpassen.

## Master-Images markieren

Images bekommen die Option **„Als Master-Image markieren“** (Rechtsklick/Details im Images-Baum, Kennzeichen in der
Liste). Die Automatisierung bietet bei *Master-Image* nur markierte Images an
(siehe [AUTOMATISIERUNG.md](AUTOMATISIERUNG.md)).

## Noch offen

- ~~Gerätename fix oder änderbar~~ → entschieden: immer der Tool-Name (ändern = Gerät umbenennen); Dialoge zeigen,
  wie der Name ankommt (Windows max. 15 Zeichen, `_` → `-`: „DoNs_EliteBook_1“ → „DoNs-EliteBook“).
- Sind Geräte in einer Domäne oder in Azure AD/Intune? (Beitritt müsste nach dem Einrichten erfolgen.)
- Nicht generalisierte 1:1-Images (Weg A: Name per Registry, Key per Skript beim ersten Start) – vorerst nicht
  vorgesehen.
