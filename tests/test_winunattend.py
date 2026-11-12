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



class ProductKeyUnattendTest(unittest.TestCase):
    def test_key_only_in_specialize(self):
        opts = wu.WinOptions(product_key="VK7JG-NPHTM-C97JM-9MPGT-3V66T")
        root = ET.fromstring(wu.build(opts, pe=False))
        spec = component(root, "specialize", "Microsoft-Windows-Shell-Setup")
        self.assertEqual(spec.find("u:ProductKey", N).text, "VK7JG-NPHTM-C97JM-9MPGT-3V66T")
        self.assertIn("Windows-Schlüssel …3V66T", " ".join(wu.summary(opts)))


if __name__ == "__main__":
    unittest.main()
