"""Spaltenbreiten merken (Ä-032): Laden, Speichern, Grenzen, kaputte Datei."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import colstate


class ColStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_save_load_per_list(self):
        self.assertEqual(colstate.load(), {})
        colstate.save("geraete", {"Gerät": 180, "Status": 220})
        colstate.save("images", {"Name": 170})
        self.assertEqual(colstate.load(), {"geraete": {"Gerät": 180, "Status": 220}, "images": {"Name": 170}})
        colstate.save("geraete", {"Gerät": 300})                       # andere Listen bleiben
        self.assertEqual(colstate.load()["images"], {"Name": 170})
        self.assertEqual(colstate.path(), Path(self.tmp.name) / "okula-recovery" / "spalten.json")

    def test_limits_and_broken_file(self):
        colstate.save("x", {"a": 5, "b": 99999, "c": 0})
        self.assertEqual(colstate.load()["x"], {"a": colstate.MIN_WIDTH, "b": colstate.MAX_WIDTH})
        colstate.path().write_text('{"x": {"a": "breit", "b": true, "c": 120}, "y": 3}')
        self.assertEqual(colstate.load(), {"x": {"c": 120}})
        colstate.path().write_text("kaputt")
        self.assertEqual(colstate.load(), {})


if __name__ == "__main__":
    unittest.main()
