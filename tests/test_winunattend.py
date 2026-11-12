import base64
import unittest
import xml.etree.ElementTree as ET

from okula_recovery import winunattend as wu

N = {"u": wu.NS, "wcm": wu.WCM}


def component(root, pass_name, name):
    for s in root.findall("u:settings", N):
        if s.get("pass") == pass_name:
            for c in s.findall("u:component", N):
                if c.get("name") == name:
                    return c
    return None


class UnattendTest(unittest.TestCase):
    def test_defaults_swiss_local_account_bypass(self):
        # Standard: Setup prüft die Windows-11-Anforderungen (Umgehen nur von Hand, mit Warnung)
        plain = ET.fromstring(wu.build(wu.WinOptions(ui_language="de-DE")))
        setup = component(plain, "windowsPE", "Microsoft-Windows-Setup")
        self.assertEqual([p.text for p in setup.iter(f"{{{wu.NS}}}Path")], [])
        self.assertNotIn("Anforderungen umgangen", " ".join(wu.summary(wu.WinOptions())))
        xml = wu.build(wu.WinOptions(ui_language="de-DE", bypass_requirements=True))
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="utf-8"?>'))
        root = ET.fromstring(xml)
        self.assertEqual([s.get("pass") for s in root.findall("u:settings", N)],
                         ["windowsPE", "specialize", "oobeSystem"])
        setup = component(root, "windowsPE", "Microsoft-Windows-Setup")
        cmds = [p.text for p in setup.iter(f"{{{wu.NS}}}Path")]
        self.assertEqual(len(cmds), 5)
        self.assertIn("BypassTPMCheck", cmds[0])
        self.assertEqual(setup.get("processorArchitecture"), "amd64")
        # Setup verlangt in UserData immer einen ProductKey (leer = wie ohne Antwortdatei fragen)
        key = setup.find("u:UserData/u:ProductKey/u:Key", N)
        self.assertIsNotNone(key)
        self.assertFalse(key.text)
        intl = component(root, "windowsPE", "Microsoft-Windows-International-Core-WinPE")
        self.assertEqual(intl.find("u:InputLocale", N).text, "0807:00000807")
        self.assertEqual(intl.find("u:UILanguage", N).text, "de-DE")
        self.assertEqual(intl.find("u:UserLocale", N).text, "de-CH")
        spec = component(root, "specialize", "Microsoft-Windows-Shell-Setup")
        self.assertEqual(spec.find("u:TimeZone", N).text, "W. Europe Standard Time")
        self.assertIsNone(spec.find("u:ComputerName", N))
        regs = " ".join(p.text for p in component(root, "specialize", "Microsoft-Windows-Deployment")
                        .iter(f"{{{wu.NS}}}Path"))
        for key in ("BypassNRO", "PreventDeviceEncryption", "DisablePrivacyExperience"):
            self.assertIn(key, regs)
        oobe = component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
        acc = oobe.find("u:UserAccounts/u:LocalAccounts/u:LocalAccount", N)
        self.assertEqual(acc.get(f"{{{wu.WCM}}}action"), "add")
        # B-012: Standardname „Okula“ (nicht „Benutzer“ – kollidiert mit der Gruppe in deutschem Windows)
        self.assertEqual(acc.find("u:Name", N).text, "Okula")
        self.assertEqual(acc.find("u:Group", N).text, "Administrators")
        self.assertEqual(acc.find("u:Password/u:PlainText", N).text, "true")
        # ohne Passwort: einmal automatisch anmelden, dann Passwort setzen lassen
        self.assertEqual(oobe.find("u:AutoLogon/u:LogonCount", N).text, "1")
        self.assertEqual(oobe.find("u:AutoLogon/u:Username", N).text, "Okula")
        first = [c.text for c in oobe.iter(f"{{{wu.NS}}}CommandLine")]
        self.assertIn('net user "Okula" /logonpasswordchg:yes', first)
        self.assertEqual(oobe.find("u:OOBE/u:ProtectYourPC", N).text, "3")

    def test_password_encoded_and_name_cleaned(self):
        opts = wu.WinOptions(local_account="Okula", password="Grüezi 1", computer_name="CompactPlayer 1 Büro",
                             swiss_region=False, ui_language="en-US")
        root = ET.fromstring(wu.build(opts))
        oobe = component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
        value = oobe.find("u:UserAccounts/u:LocalAccounts/u:LocalAccount/u:Password/u:Value", N).text
        self.assertEqual(base64.b64decode(value).decode("utf-16-le"), "Grüezi 1Password")
        self.assertIsNone(oobe.find("u:AutoLogon", N))
        self.assertEqual(component(root, "specialize", "Microsoft-Windows-Shell-Setup")
                         .find("u:ComputerName", N).text, "CompactPlayer-1")
        intl = component(root, "oobeSystem", "Microsoft-Windows-International-Core")
        self.assertEqual(intl.find("u:InputLocale", N).text, "en-US")
        self.assertEqual(wu.computer_name("12345"), "")
        self.assertEqual(wu.computer_name("PC-Empfang-Zürich-2"), "PC-Empfang-Zuer")

    def test_everything_off(self):
        opts = wu.WinOptions(bypass_requirements=False, local_account="", skip_privacy=False, no_bitlocker=False)
        root = ET.fromstring(wu.build(opts))
        self.assertIsNone(component(root, "specialize", "Microsoft-Windows-Deployment"))
        self.assertEqual(list(component(root, "windowsPE", "Microsoft-Windows-Setup").iter(f"{{{wu.NS}}}Path")), [])
        oobe = component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
        self.assertIsNone(oobe.find("u:UserAccounts", N))
        self.assertEqual(wu.summary(opts), ["Region Schweiz: Formate de-CH, Tastatur Schweiz, Zeitzone Zürich"])


class KontonameTest(unittest.TestCase):
    """B-012: Kontonamen, die Windows nicht anlegen kann, vor dem Start abfangen."""

    def test_default_ok(self):
        self.assertEqual(wu.WinOptions().local_account, "Okula")
        self.assertIsNone(wu.pruefe_kontoname(wu.WinOptions().local_account))

    def test_reserved_names(self):
        for name in ("Benutzer", "benutzer", " Benutzer ", "BENUTZER", "Administrator", "administratoren", "Gast",
                     "Gäste", "GÄSTE", "Jeder", "Users", "user", "Administrators", "Guest", "Guests", "Everyone",
                     "SYSTEM", "Network", "Local", "Default", "DefaultAccount", "WDAGUtilityAccount", "Konto",
                     "Benutzerin", "Administrator-Gruppe", "Administratoren-Gruppe"):
            msg = wu.pruefe_kontoname(name)
            self.assertIsNotNone(msg, name)
            self.assertIn(f"„{name.strip()}“", msg)
            self.assertIn("Anderen Benutzernamen eingeben", msg)

    def test_ok_names(self):
        for name in ("Okula", "Dominik", "Büro", "Empfang 2", "max.muster", "Benutzer1", "Admin", "a" * 20, ""):
            self.assertIsNone(wu.pruefe_kontoname(name), name)

    def test_empty_allowed(self):
        # leer: kein Konto in der Antwortdatei, Windows fragt beim ersten Start selbst
        self.assertIsNone(wu.pruefe_kontoname("   "))
        self.assertIsNone(wu.pruefe_kontoname(None))

    def test_length_dot_chars(self):
        self.assertIn("zu lang", wu.pruefe_kontoname("a" * 21))
        self.assertIn("Punkt", wu.pruefe_kontoname("Okula."))
        for c in '"/\\[]:;|=,+*?<>':
            msg = wu.pruefe_kontoname(f"Ok{c}ula")
            self.assertIsNotNone(msg, c)
            self.assertIn(c, msg)

    def test_name_in_xml(self):
        for name in ("Okula", "Empfang"):
            root = ET.fromstring(wu.build(wu.WinOptions(local_account=name)))
            oobe = component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
            acc = oobe.find("u:UserAccounts/u:LocalAccounts/u:LocalAccount", N)
            self.assertEqual(acc.find("u:Name", N).text, name)
            self.assertEqual(acc.find("u:DisplayName", N).text, name)
            self.assertIn(f'net user "{name}" /logonpasswordchg:yes',
                          [c.text for c in oobe.iter(f"{{{wu.NS}}}CommandLine")])
            self.assertNotIn("Benutzer", ET.tostring(acc, encoding="unicode"))



def structure(xml: str) -> list[str]:
    """Alle Elemente als „Durchgang|Komponente|Pfad[=Text]“ in Dokumentreihenfolge."""
    out = []
    for s in ET.fromstring(xml):
        for c in s:
            def walk(el, prefix):
                for ch in el:
                    path = f"{prefix}/{ch.tag.split('}')[1]}" if prefix else ch.tag.split('}')[1]
                    out.append(f"{s.get('pass')}|{c.get('name')}|{path}"
                               + (f"={ch.text}" if ch.text and len(ch) == 0 else ""))
                    walk(ch, path)
            walk(c, "")
    return out


SPEC = "specialize|Microsoft-Windows-Deployment|RunSynchronous"
OOBE = "oobeSystem|Microsoft-Windows-Shell-Setup|"
# I-038: Antwortdatei der Direktinstallation ohne Audit-Modus – Stand vor I-038 (darf sich nicht ändern)
EXPECTED_DIRECT = [
    "specialize|Microsoft-Windows-Shell-Setup|ComputerName=PC-1",
    "specialize|Microsoft-Windows-Shell-Setup|ProductKey=VK7JG-NPHTM-C97JM-9MPGT-3V66T",
    "specialize|Microsoft-Windows-Shell-Setup|TimeZone=W. Europe Standard Time",
    SPEC,
    SPEC + "/RunSynchronousCommand", SPEC + "/RunSynchronousCommand/Order=1",
    SPEC + "/RunSynchronousCommand/Path=reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\OOBE "
           "/v BypassNRO /t REG_DWORD /d 1 /f",
    SPEC + "/RunSynchronousCommand", SPEC + "/RunSynchronousCommand/Order=2",
    SPEC + "/RunSynchronousCommand/Path=reg add HKLM\\SYSTEM\\CurrentControlSet\\Control\\BitLocker "
           "/v PreventDeviceEncryption /t REG_DWORD /d 1 /f",
    SPEC + "/RunSynchronousCommand", SPEC + "/RunSynchronousCommand/Order=3",
    SPEC + "/RunSynchronousCommand/Path=reg add HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\OOBE "
           "/v DisablePrivacyExperience /t REG_DWORD /d 1 /f",
    "oobeSystem|Microsoft-Windows-International-Core|InputLocale=0807:00000807",
    "oobeSystem|Microsoft-Windows-International-Core|SystemLocale=de-CH",
    "oobeSystem|Microsoft-Windows-International-Core|UILanguage=de-DE",
    "oobeSystem|Microsoft-Windows-International-Core|UserLocale=de-CH",
    OOBE + "OOBE", OOBE + "OOBE/HideEULAPage=true", OOBE + "OOBE/HideOnlineAccountScreens=true",
    OOBE + "OOBE/HideLocalAccountScreen=true", OOBE + "OOBE/HideWirelessSetupInOOBE=true",
    OOBE + "OOBE/ProtectYourPC=3",
    OOBE + "UserAccounts", OOBE + "UserAccounts/LocalAccounts", OOBE + "UserAccounts/LocalAccounts/LocalAccount",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/Name=Okula",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/DisplayName=Okula",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/Group=Administrators",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/Password",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/Password/Value",
    OOBE + "UserAccounts/LocalAccounts/LocalAccount/Password/PlainText=true",
    OOBE + "AutoLogon", OOBE + "AutoLogon/Password", OOBE + "AutoLogon/Password/Value",
    OOBE + "AutoLogon/Password/PlainText=true", OOBE + "AutoLogon/Enabled=true", OOBE + "AutoLogon/LogonCount=1",
    OOBE + "AutoLogon/Username=Okula",
    OOBE + "FirstLogonCommands", OOBE + "FirstLogonCommands/SynchronousCommand",
    OOBE + "FirstLogonCommands/SynchronousCommand/Order=1",
    OOBE + 'FirstLogonCommands/SynchronousCommand/CommandLine=net user "Okula" /logonpasswordchg:yes',
    OOBE + "FirstLogonCommands/SynchronousCommand", OOBE + "FirstLogonCommands/SynchronousCommand/Order=2",
    OOBE + "FirstLogonCommands/SynchronousCommand/CommandLine=net accounts /maxpwage:unlimited",
]
DIRECT_OPTS = dict(ui_language="de-DE", computer_name="PC-1", product_key="VK7JG-NPHTM-C97JM-9MPGT-3V66T",
                   skip_network=True)


class DirectUnchangedTest(unittest.TestCase):
    def test_structure_without_audit(self):
        self.assertEqual(structure(wu.build(wu.WinOptions(**DIRECT_OPTS), pe=False)), EXPECTED_DIRECT)
        self.assertEqual(structure(wu.build(wu.WinOptions(**DIRECT_OPTS, audit_mode=False), pe=False)),
                         EXPECTED_DIRECT)
        self.assertNotIn("Audit", " ".join(wu.summary(wu.WinOptions(**DIRECT_OPTS))))


class AuditModeTest(unittest.TestCase):
    """I-038: Direktinstallation für ein Master-Image – Windows startet im Audit-Modus."""

    def setUp(self):
        # Konto, Name und Schlüssel bewusst gesetzt: Audit-Modus hat Vorrang
        self.opts = wu.WinOptions(**DIRECT_OPTS, password="geheim", audit_mode=True)
        self.xml = wu.build(self.opts, pe=False, audit_commands=["cmd /c aufraeumen.cmd"])
        self.root = ET.fromstring(self.xml)

    def test_passes_and_reseal(self):
        self.assertEqual([s.get("pass") for s in self.root], ["specialize", "auditUser", "oobeSystem"])
        oobe = [c.get("name") for s in self.root if s.get("pass") == "oobeSystem" for c in s]
        self.assertEqual(oobe, ["Microsoft-Windows-Deployment"])  # alles andere ignoriert Windows bei Reseal
        mode = component(self.root, "oobeSystem", "Microsoft-Windows-Deployment").find("u:Reseal/u:Mode", N)
        self.assertEqual(mode.text, "Audit")
        self.assertNotIn("ForceShutdownNow", self.xml)

    def test_no_account_name_key(self):
        for tag in ("LocalAccount", "AutoLogon", "ComputerName", "ProductKey", "FirstLogonCommands", "BypassNRO",
                    ">Okula<", "PC-1", "VK7JG", wu.encode_password("geheim")):
            self.assertNotIn(tag, self.xml, tag)

    def test_region_bitlocker_privacy_kept(self):
        spec = component(self.root, "specialize", "Microsoft-Windows-Shell-Setup")
        self.assertEqual(spec.find("u:TimeZone", N).text, "W. Europe Standard Time")
        intl = component(self.root, "specialize", "Microsoft-Windows-International-Core")
        self.assertEqual(intl.find("u:InputLocale", N).text, "0807:00000807")
        self.assertEqual(intl.find("u:UserLocale", N).text, "de-CH")
        regs = " ".join(p.text for p in component(self.root, "specialize", "Microsoft-Windows-Deployment")
                        .iter(f"{{{wu.NS}}}Path"))
        self.assertIn("PreventDeviceEncryption", regs)
        self.assertIn("DisablePrivacyExperience", regs)
        off = wu.build(wu.WinOptions(audit_mode=True, no_bitlocker=False, skip_privacy=False, swiss_region=False,
                                     ui_language=""), pe=False)
        self.assertNotIn("PreventDeviceEncryption", off)
        self.assertNotIn("International-Core", off)

    def test_audit_user_commands(self):
        audit = component(self.root, "auditUser", "Microsoft-Windows-Deployment")
        cmds = audit.findall("u:RunSynchronous/u:RunSynchronousCommand", N)
        self.assertEqual([c.find("u:Order", N).text for c in cmds], ["1", "2", "3"])
        paths = [c.find("u:Path", N).text for c in cmds]
        self.assertEqual(paths[0], "cmd /c aufraeumen.cmd")  # zuerst Aufräumen, dann Antwortdatei löschen
        self.assertEqual(paths[1], 'cmd /c del /f /q "%WINDIR%\\Panther\\unattend.xml"')
        self.assertIn("del /f /q %WINDIR%\\Panther\\unattend.xml", paths[2])
        self.assertTrue(paths[2].startswith('cmd /c start "Okula" /min '))
        # ohne Zusatzbefehle (z. B. Boot-Stick): nur das Löschen
        plain = ET.fromstring(wu.build(wu.WinOptions(audit_mode=True), pe=False))
        self.assertEqual(len(component(plain, "auditUser", "Microsoft-Windows-Deployment")
                             .findall("u:RunSynchronous/u:RunSynchronousCommand", N)), 2)

    def test_pe_part_unchanged(self):
        self.assertEqual(wu.build(self.opts, pe=True, system=False, launch="x"),
                         wu.build(wu.WinOptions(**DIRECT_OPTS), pe=True, system=False, launch="x"))

    def test_summary(self):
        lines = wu.summary(self.opts)
        self.assertEqual(lines[0], "Startet im Audit-Modus für ein Master-Image (kein Konto, kein Computername, "
                                   "kein Schlüssel)")
        text = " ".join(lines)
        for word in ("Lokales Konto", "Computername PC-1", "Windows-Schlüssel …"):
            self.assertNotIn(word, text)
        self.assertIn("Keine automatische BitLocker-Verschlüsselung", text)
        self.assertIn("Region Schweiz", text)
        self.assertIn("sysprep.exe /generalize /oobe /shutdown", wu.AUDIT_NEXT_STEPS)

    def test_master_unattend_unchanged(self):
        # Zurückspielen eines Master-Images startet nie im Audit-Modus
        xml = wu.master_unattend("PC-1", "VK7JG-NPHTM-C97JM-9MPGT-3V66T", account="Okula")
        self.assertNotIn("Reseal", xml)
        self.assertNotIn("auditUser", xml)
        self.assertIn("PC-1", xml)


class ProductKeyUnattendTest(unittest.TestCase):
    def test_key_only_in_specialize(self):
        opts = wu.WinOptions(product_key="VK7JG-NPHTM-C97JM-9MPGT-3V66T")
        root = ET.fromstring(wu.build(opts, pe=False))
        spec = component(root, "specialize", "Microsoft-Windows-Shell-Setup")
        self.assertEqual(spec.find("u:ProductKey", N).text, "VK7JG-NPHTM-C97JM-9MPGT-3V66T")
        self.assertIn("Windows-Schlüssel …3V66T", " ".join(wu.summary(opts)))


if __name__ == "__main__":
    unittest.main()
