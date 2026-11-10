"""Projektübersicht (I-034): kleiner Webserver im Tool-Prozess, nur auf 127.0.0.1, mit Token in der URL.

Seiten (HTML/CSS/JS) liegen im Paket unter ``assets/projekt/``. Lesen: ``GET /<token>/api/daten``.
Schreiben nur per ``POST`` mit JSON (``Content-Type: application/json``) – eine fremde Webseite kann ohne
Token und ohne CORS-Vorabprüfung nichts speichern. Der Server ändert nie die Markdown-Dateien.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from okula_recovery import projekt

ASSETS = Path(__file__).resolve().parent / "assets" / "projekt"
FILES = {"": ("index.html", "text/html; charset=utf-8"),
         "app.js": ("app.js", "text/javascript; charset=utf-8"),
         "style.css": ("style.css", "text/css; charset=utf-8")}
MAX_BODY = 256 * 1024
HOST = "127.0.0.1"


class ProjectServer:
    """Startet einmal pro Tool-Prozess; ``url`` bleibt gleich (gleicher Port, gleiches Token)."""

    def __init__(self, folder: Callable[[], Path], store: projekt.FeedbackStore | None = None):
        self.folder = folder
        self.store = store or projekt.FeedbackStore()
        self.token = secrets.token_urlsafe(24)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/{self.token}/"

    def start(self) -> str:
        if self.httpd is None:
            server = self

            class _Handler(Handler):
                owner = server

            self.httpd = ThreadingHTTPServer((HOST, 0), _Handler)
            self.httpd.daemon_threads = True
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="projektuebersicht", daemon=True)
            self.thread.start()
        return self.url

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


class Handler(BaseHTTPRequestHandler):
    server_version = "OkulaProjekt"
    owner: ProjectServer

    def log_message(self, format: str, *args) -> None:  # kein Rauschen auf stderr (Token in der URL)
        pass

    # ---------- Prüfungen ----------

    def _route(self) -> str | None:
        """Pfad nach dem Token; None = abgewiesen (403 schon gesendet)."""
        if self.client_address[0] != HOST:
            self._send(403, {"fehler": "nur lokal"})
            return None
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"{HOST}:{self.owner.port}", f"localhost:{self.owner.port}"):
            self._send(403, {"fehler": "falscher Host"})      # DNS-Rebinding
            return None
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        prefix = f"/{self.owner.token}/"
        if not secrets.compare_digest(path[:len(prefix)].encode("utf-8"), prefix.encode("utf-8")):
            self._send(403, {"fehler": "Zugriff verweigert"})
            return None
        return path[len(prefix):]

    # ---------- Antworten ----------

    def _headers(self, status: int, ctype: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    # ---------- GET ----------

    def do_GET(self) -> None:
        route = self._route()
        if route is None:
            return
        if route == "api/daten":
            self._send(200, projekt.page_data(self.owner.folder(), self.owner.store))
            return
        if route not in FILES:
            self._send(404, {"fehler": "nicht gefunden"})
            return
        name, ctype = FILES[route]
        try:
            body = (ASSETS / name).read_bytes()
        except OSError:
            self._send(404, {"fehler": "nicht gefunden"})
            return
        self._headers(200, ctype, len(body))
        self.wfile.write(body)

    # ---------- POST ----------

    def do_POST(self) -> None:
        route = self._route()
        if route is None:
            return
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            self._send(415, {"fehler": "nur JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            self._send(413, {"fehler": "Anfrage zu gross oder leer"})
            return
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:
            self._send(400, {"fehler": "ungültiges JSON"})
            return
        store = self.owner.store
        try:
            if route == "api/rueckmeldung":
                fields = {k: req[k] for k in ("haken", "kommentar", "prio_wunsch", "status_wunsch") if k in req}
                entry = store.save_entry(str(req.get("key", "")), str(req.get("art", "")),
                                         str(req.get("bezug", "")), str(req.get("text", "")), fields)
                self._send(200, {"ok": True, "eintrag": entry})
            elif route == "api/notiz":
                action = req.get("aktion")
                if action == "neu":
                    self._send(200, {"ok": True, "notiz": store.add_note(str(req.get("art", "")),
                                                                         str(req.get("text", "")))})
                elif action == "aendern":
                    self._send(200, {"ok": True, "notiz": store.update_note(str(req.get("id", "")),
                                                                            str(req.get("art", "")),
                                                                            str(req.get("text", "")))})
                elif action == "loeschen":
                    store.delete_note(str(req.get("id", "")))
                    self._send(200, {"ok": True})
                else:
                    self._send(400, {"fehler": "unbekannte Aktion"})
            else:
                self._send(404, {"fehler": "nicht gefunden"})
        except projekt.FeedbackError as e:
            self._send(400, {"fehler": str(e)})
        except OSError as e:
            self._send(500, {"fehler": f"Speichern fehlgeschlagen: {e.strerror or e}"})
