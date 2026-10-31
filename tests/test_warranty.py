"""Garantie-Abfrage (I-025): Auswertung, Anzeige, Schlüsselablage, Abfragen mit gemockten Antworten."""

import json
import os
import stat
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from okula_recovery import devices, warranty

TODAY = date(2026, 10, 31)


def inv(vendor="Dell Inc.", serial="ABC1234", sku=""):
    return {"dmi": {"sys_vendor": vendor, "product_serial": serial, "product_sku": sku}}


DELL_ANSWER = [{"id": 1, "serviceTag": "ABC1234", "invalid": False, "productLineDescription": "LATITUDE 5420",
                "entitlements": [
                    {"serviceLevelDescription": "Basic Onsite", "startDate": "2021-03-01T00:00:00Z",
                     "endDate": "2024-03-01T23:59:59.999Z", "entitlementType": "INITIAL"},
                    {"serviceLevelDescription": "ProSupport", "startDate": "2021-03-01T00:00:00Z",
                     "endDate": "2027-02-28T23:59:59.999Z", "entitlementType": "EXTENDED"}]}]
HP_ANSWER = [{"product": {"serialNumber": "5CG1234XYZ", "productNumber": "5ZH12EA"},
              "offers": [{"offerDescription": "HP Hardware Maintenance Onsite Support",
                          "serviceObligationLineItemStartDate": "2022-01-10",
                          "serviceObligationLineItemEndDate": "2025-01-09"},
                         {"offerDescription": "Wolf Security", "serviceObligationLineItemStartDate": "2022-01-10",
                          "serviceObligationLineItemEndDate": "2023-01-09"}]}]
LENOVO_ANSWER = {"code": 0, "msg": "success", "data": {
    "machineInfo": {"serial": "PF2ABCDE", "product": "20XW"},
    "baseWarranties": [{"name": "Depot", "startDate": "2021-06-01", "endDate": "2024-05-31"}],
    "upmaWarranties": [{"name": "Premier Support", "startDate": "2024-06-01", "endDate": "2026-12-15"}]}}


class FakeHttp:
    """Gibt vorbereitete Antworten der Reihe nach zurück und merkt sich die Anfragen."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        code, data = self.answers.pop(0)
        return code, data if isinstance(data, bytes) else json.dumps(data).encode()


class VendorTest(unittest.TestCase):
    def test_vendor_and_serial(self):
        self.assertEqual(warranty.vendor_of(inv("Dell Inc.")), "dell")
        self.assertEqual(warranty.vendor_of(inv("HP")), "hp")
        self.assertEqual(warranty.vendor_of(inv("Hewlett-Packard")), "hp")
        self.assertEqual(warranty.vendor_of(inv("LENOVO")), "lenovo")
        self.assertEqual(warranty.vendor_of(inv("ASUSTeK COMPUTER INC.")), "")
        self.assertEqual(warranty.vendor_of({}), "")
        self.assertEqual(warranty.serial_of(inv(serial=" ABC1234 ")), "ABC1234")
        for dummy in ("To be filled by O.E.M.", "Default string", "0", "", "a b c", "x" * 40):
            self.assertEqual(warranty.serial_of(inv(serial=dummy)), "", dummy)
        self.assertTrue(warranty.supported(inv()))
        self.assertFalse(warranty.supported(inv("ASUS")))
        self.assertEqual(warranty.hp_product(inv(sku="5ZH12EA#UUZ")), "5ZH12EA#UUZ")
        self.assertEqual(warranty.hp_product(inv(sku="Default string;x")), "")


class StatusTest(unittest.TestCase):
    def test_levels(self):
        def w(d):
            return {"until": d.isoformat(), "source": "dell"}
        self.assertEqual(warranty.status(w(TODAY + timedelta(days=200)), TODAY), ("ok", "19.05.2027"))
        level, text = warranty.status(w(TODAY + timedelta(days=90)), TODAY)
        self.assertEqual(level, "warn")
        self.assertIn("läuft in 90 Tagen ab", text)
        self.assertIn("1 Tag ab", warranty.status(w(TODAY + timedelta(days=1)), TODAY)[1])
        self.assertEqual(warranty.status(w(TODAY), TODAY)[0], "warn")
        self.assertEqual(warranty.status(w(TODAY - timedelta(days=1)), TODAY),
                         ("expired", "30.10.2026 – abgelaufen"))
        self.assertEqual(warranty.status({}, TODAY), ("unknown", "unbekannt"))
        self.assertEqual(warranty.status(None, TODAY)[0], "unknown")

    def test_parse_date(self):
        self.assertEqual(warranty.parse_date("2027-02-28T23:59:59.999Z"), date(2027, 2, 28))
        self.assertEqual(warranty.parse_date("31.03.2027"), date(2027, 3, 31))
        self.assertEqual(warranty.parse_date("1.4.2027"), date(2027, 4, 1))
        for bad in ("", None, "morgen", "2027-02-30", "31.13.2027", 5):
            self.assertIsNone(warranty.parse_date(bad), bad)

    def test_manual_fresh_describe_merge(self):
        m = warranty.manual("31.03.2027")
        self.assertEqual((m["until"], m["source"]), ("2027-03-31", "manual"))
        self.assertEqual(warranty.manual("  "), {})
        with self.assertRaises(warranty.WarrantyError):
            warranty.manual("März 2027")
        self.assertTrue(warranty.fresh(m))
        self.assertIn("von Hand", warranty.describe(m))
        self.assertIn("eingetragen", warranty.describe(m))

        old = warranty.result("dell", date(2027, 2, 28), service="ProSupport")
        self.assertTrue(warranty.fresh(old))
        old["checked"] = (datetime.now() - timedelta(days=31)).isoformat(timespec="seconds")
        self.assertFalse(warranty.fresh(old))
        self.assertIn("älter als 30 Tage", warranty.describe(old))
        self.assertIn("(Dell, ProSupport)", warranty.describe(old))
        self.assertFalse(warranty.fresh({}))

        # Fehler: altes Ergebnis bleibt, Fehler wird vermerkt
        kept = warranty.merge(old, None, "keine Verbindung")
        self.assertEqual((kept["until"], kept["error"]), ("2027-02-28", "keine Verbindung"))
        self.assertIn("Letzte Abfrage: keine Verbindung", warranty.describe(kept))
        new = warranty.result("dell", date(2028, 1, 1))
        self.assertIs(warranty.merge(old, new), new)
        self.assertEqual(warranty.merge({}, None, "x"), {"error": "x"})
        self.assertEqual(warranty.describe({}), "unbekannt")


class ParserTest(unittest.TestCase):
    def test_dell(self):
        self.assertEqual(warranty.parse_dell(DELL_ANSWER), (date(2021, 3, 1), date(2027, 2, 28), "ProSupport"))
        with self.assertRaisesRegex(warranty.WarrantyError, "unbekannt"):
            warranty.parse_dell([{"serviceTag": "X", "invalid": True, "entitlements": []}])
        with self.assertRaisesRegex(warranty.WarrantyError, "keine Garantie"):
            warranty.parse_dell([{"serviceTag": "X", "entitlements": []}])
        with self.assertRaises(warranty.WarrantyError):
            warranty.parse_dell([])

    def test_hp(self):
        self.assertEqual(warranty.parse_hp(HP_ANSWER),
                         (date(2022, 1, 10), date(2025, 1, 9), "HP Hardware Maintenance Onsite Support"))
        with self.assertRaises(warranty.WarrantyError):
            warranty.parse_hp([{"product": {}, "offers": []}])

    def test_lenovo(self):
        self.assertEqual(warranty.parse_lenovo(LENOVO_ANSWER),
                         (date(2024, 6, 1), date(2026, 12, 15), "Premier Support"))
        with self.assertRaisesRegex(warranty.WarrantyError, "invalid serial"):
            warranty.parse_lenovo({"code": 1, "msg": "invalid serial", "data": None})
        with self.assertRaises(warranty.WarrantyError):
            warranty.parse_lenovo([])


class QueryTest(unittest.TestCase):
    def test_dell(self):
        send = FakeHttp((200, {"access_token": "T0K", "expires_in": 3600}), (200, DELL_ANSWER))
        r = warranty.query_dell("ABC1234", "cid", "csecret", send)
        self.assertEqual((r["until"], r["source"], r["service"]), ("2027-02-28", "dell", "ProSupport"))
        (m1, u1, b1, _h1), (m2, u2, b2, h2) = send.calls
        self.assertEqual((m1, u1), ("POST", warranty.DELL_TOKEN))
        self.assertIn(b"client_id=cid", b1)
        self.assertIn(b"grant_type=client_credentials", b1)
        self.assertEqual(m2, "GET")
        self.assertTrue(u2.startswith(warranty.DELL_WARRANTY) and u2.endswith("servicetags=ABC1234"))
        self.assertEqual(h2["Authorization"], "Bearer T0K")
        self.assertIsNone(b2)

    def test_dell_errors(self):
        with self.assertRaisesRegex(warranty.WarrantyError, "Zugang abgelehnt"):
            warranty.query_dell("ABC1234", "x", "y", FakeHttp((401, {"error": "invalid_client"})))
        with self.assertRaisesRegex(warranty.WarrantyError, "kein Token"):
            warranty.query_dell("ABC1234", "x", "y", FakeHttp((200, {})))
        with self.assertRaisesRegex(warranty.WarrantyError, "kein JSON"):
            warranty.query_dell("ABC1234", "x", "y", FakeHttp((200, {"access_token": "t"}), (200, b"<html>")))
        with self.assertRaisesRegex(warranty.WarrantyError, "zu viele"):
            warranty.query_dell("ABC1234", "x", "y", FakeHttp((200, {"access_token": "t"}), (429, b"")))

    def test_hp(self):
        send = FakeHttp((200, {"access_token": "H"}), (200, HP_ANSWER))
        r = warranty.query_hp("5CG1234XYZ", "key", "sec", "5ZH12EA#UUZ", send)
        self.assertEqual((r["until"], r["source"]), ("2025-01-09", "hp"))
        (_m1, u1, b1, h1), (m2, u2, b2, h2) = send.calls
        self.assertEqual(u1, warranty.HP_TOKEN)
        self.assertEqual(h1["Authorization"], "Basic a2V5OnNlYw==")   # key:sec
        self.assertEqual(b1, b"grant_type=client_credentials")
        self.assertEqual((m2, u2, h2["Authorization"]), ("POST", warranty.HP_QUERY, "Bearer H"))
        self.assertEqual(json.loads(b2), [{"sn": "5CG1234XYZ", "pn": "5ZH12EA#UUZ"}])

    def test_lenovo(self):
        send = FakeHttp((200, LENOVO_ANSWER))
        r = warranty.query_lenovo("PF2ABCDE", send)
        self.assertEqual((r["until"], r["source"], r["service"]), ("2026-12-15", "lenovo", "Premier Support"))
        self.assertEqual(json.loads(send.calls[0][2])["serialNumber"], "PF2ABCDE")

    def test_no_internet(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Name or service not known")):
            with self.assertRaisesRegex(warranty.WarrantyError, "keine Verbindung.*von Hand"):
                warranty.query_lenovo("PF2ABCDE")

    def test_lookup_dispatch(self):
        # Lenovo direkt, ohne Root-Helfer
        helper = mock.Mock(side_effect=AssertionError("kein Helfer für Lenovo"))
        r = warranty.lookup(inv("LENOVO", "PF2ABCDE"), helper, FakeHttp((200, LENOVO_ANSWER)))
        self.assertEqual(r["until"], "2026-12-15")
        # Dell/HP über den Root-Helfer: nur Hersteller, Seriennummer, Produktnummer – keine Schlüssel
        answer = warranty.result("hp", date(2025, 1, 9))
        helper = mock.Mock(return_value=(True, json.dumps(answer)))
        self.assertEqual(warranty.lookup(inv("HP", "5CG1234XYZ", "5ZH12EA#UUZ"), helper), answer)
        helper.assert_called_once_with(["query", "--vendor", "hp", "--serial", "5CG1234XYZ",
                                        "--product", "5ZH12EA#UUZ"])
        helper = mock.Mock(return_value=(False, "kein Dell-Schlüssel – in Menü → Einstellungen eintragen"))
        with self.assertRaisesRegex(warranty.WarrantyError, "kein Dell-Schlüssel"):
            warranty.lookup(inv(), helper)
        with self.assertRaisesRegex(warranty.WarrantyError, "nur für Dell, HP und Lenovo.*ASUS"):
            warranty.lookup(inv("ASUS"), helper)
        with self.assertRaisesRegex(warranty.WarrantyError, "Seriennummer"):
            warranty.lookup(inv(serial="Default string"), helper)
        with self.assertRaisesRegex(warranty.WarrantyError, "unlesbar"):
            warranty.lookup(inv(), mock.Mock(return_value=(True, "kaputt")))


class KeyStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "okula-recovery" / "warranty.cred"

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_0600_and_delete(self):
        self.assertEqual(warranty.read_keys(self.path), {})
        self.assertIn("gespeichert", warranty.set_key("dell", "cid", "csecret", self.path))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        warranty.set_key("hp", "k", "s", self.path)
        self.assertEqual(warranty.read_keys(self.path), {"dell": {"id": "cid", "secret": "csecret"},
                                                         "hp": {"id": "k", "secret": "s"}})
        self.assertIn("gelöscht", warranty.set_key("dell", "", "", self.path))
        self.assertEqual(set(warranty.read_keys(self.path)), {"hp"})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        for bad in (("dell", "cid", ""), ("dell", "a b", "x"), ("dell", "x", "a\nb"), ("lenovo", "a", "b")):
            with self.assertRaises(warranty.WarrantyError, msg=bad):
                warranty.set_key(*bad, path=self.path)

    def test_root_query_uses_stored_key(self):
        with self.assertRaisesRegex(warranty.WarrantyError, "kein Dell-Schlüssel"):
            warranty.root_query("dell", "ABC1234", path=self.path)
        warranty.set_key("dell", "cid", "csecret", self.path)
        send = FakeHttp((200, {"access_token": "T"}), (200, DELL_ANSWER))
        self.assertEqual(warranty.root_query("dell", "ABC1234", path=self.path, send=send)["until"], "2027-02-28")
        self.assertIn(b"client_secret=csecret", send.calls[0][2])
        with self.assertRaisesRegex(warranty.WarrantyError, "Seriennummer ungültig"):
            warranty.root_query("dell", "ABC;rm -rf /", path=self.path)

    def test_helper_output(self):
        """Root-Helfer: „keys“ verrät nur Hersteller, nie Schlüssel; Schlüssel kommen über stdin."""
        with mock.patch.object(warranty, "CRED_FILE", self.path), mock.patch("os.geteuid", return_value=0), \
                mock.patch("sys.stdin") as stdin, mock.patch("builtins.print") as out:
            stdin.read.return_value = "cid\ncsecret\n"
            self.assertEqual(warranty.main(["set-key", "--vendor", "dell", "--stdin"]), 0)
            self.assertEqual(warranty.main(["keys"]), 0)
            printed = [c.args[0] for c in out.call_args_list]
            self.assertEqual(printed, ["OK Dell-Schlüssel gespeichert", "OK dell"])
            self.assertNotIn("csecret", " ".join(printed))
            self.assertEqual(warranty.main(["query", "--vendor", "dell", "--serial", "bad serial!"]), 1)
            self.assertTrue(out.call_args.args[0].startswith("ERROR Seriennummer ungültig"))
        with mock.patch("os.geteuid", return_value=1000), mock.patch("builtins.print") as out:
            self.assertEqual(warranty.main(["keys"]), 1)

    def test_configured_parses_vendor_list(self):
        with mock.patch.object(warranty, "call_helper", return_value=(True, "dell,hp")):
            self.assertEqual(warranty.configured(), ({"dell", "hp"}, ""))
        with mock.patch.object(warranty, "call_helper", return_value=(True, "-")):
            self.assertEqual(warranty.configured(), (set(), ""))
        with mock.patch.object(warranty, "call_helper", return_value=(False, "Helfer fehlt")):
            self.assertEqual(warranty.configured(), (set(), "Helfer fehlt"))


class DeviceFieldTest(unittest.TestCase):
    def test_saved_with_device_and_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = devices.DeviceStore(Path(tmp))
            a, _ = store.register("a1", "10.0.0.5", "", {"dmi": {"product_uuid": "11111111-1111-1111-1111-111111111111"}})
            a.warranty = warranty.manual("31.03.2027")
            store.save(a)
            again = devices.DeviceStore(Path(tmp)).devices[a.id]
            self.assertEqual(again.warranty["until"], "2027-03-31")
            b, _ = store.register("b1", "10.0.0.6", "", {"dmi": {"product_uuid": "22222222-2222-2222-2222-222222222222"}})
            store.merge(b, a)
            self.assertEqual(b.warranty["until"], "2027-03-31")

    def test_no_keys_in_export(self):
        """Der Gesamt-Export enthält Geräte (mit Garantie-Datum), aber nie warranty.cred."""
        import inspect

        from okula_recovery import transfer
        self.assertNotIn("warranty.cred", inspect.getsource(transfer))
        self.assertNotIn("CRED_FILE", inspect.getsource(transfer))


if __name__ == "__main__":
    unittest.main()
