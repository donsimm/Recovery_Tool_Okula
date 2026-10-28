"""Dialoge für Datei-Backups: Backup erstellen (Benutzerdaten, Partitionen, eigene Ordner) und zurückspielen
(ins installierte System oder herunterladen)."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import agentclient, backups, nas  # noqa: E402
from okula_recovery.uikit import scrolled  # noqa: E402

PLACEHOLDER = "…"


def _bg(work, done) -> None:
    def run():
        try:
            result = work()
        except Exception as e:  # Agent, Netzwerk, NAS – im Dialog anzeigen
            result = e
        GLib.idle_add(done, result)
    threading.Thread(target=run, daemon=True).start()


def _check_column(view: Gtk.TreeView, store, col: int, toggled) -> None:
    cell = Gtk.CellRendererToggle()
    cell.connect("toggled", toggled)
    view.append_column(Gtk.TreeViewColumn("", cell, active=col))


def _set_children(store: Gtk.TreeStore, it, col: int, value: bool) -> None:
    child = store.iter_children(it)
    while child is not None:
        store[child][col] = value
        _set_children(store, child, col, value)
        child = store.iter_next(child)


class BackupDialog(Gtk.Dialog):
    """start_job(disk, quellen, art, ablage, beschreibung, notiz)."""

    def __init__(self, parent: Gtk.Window, agent, device, nas_root: str,
                 start_job: Callable[[str, list[dict], str, str, list[str], str], None]):
        super().__init__(title="Backup erstellen", transient_for=parent, modal=True)
        self.set_default_size(820, 760)
        self.agent, self.device, self.nas_root, self.start_job = agent, device, nas_root, start_job
        self.key = agentclient.load_or_create_key()
        self.partitions: list[dict] = []
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Backup erstellen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("suggested-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self._on_response)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"Gerät: <b>{GLib.markup_escape_text(device.name)}</b>  ({agent.ip})  · Ziel: NAS: /"
                        f"{backups.BACKUP_DIR}/{GLib.markup_escape_text(agentclient.safe_name(device.name))}/…")
        box.pack_start(head, False, False, 0)

        self.tabs = Gtk.Notebook()
        self.tabs.append_page(self._build_profiles(), Gtk.Label(label="Benutzerdaten"))
        self.tabs.append_page(self._build_partitions(), Gtk.Label(label="Ganze Partitionen"))
        self.tabs.append_page(self._build_folders(), Gtk.Label(label="Eigene Ordner"))
        self.tabs.connect("switch-page", lambda *_a: GLib.idle_add(self._update))
        box.pack_start(self.tabs, True, True, 0)

        store_box = Gtk.Box(spacing=12)
        store_box.pack_start(Gtk.Label(label="Ablage:"), False, False, 0)
        self.as_files = Gtk.RadioButton.new_with_label(None, "Normale Dateien (im Reiter „Dateien“ durchsuchbar)")
        self.as_tar = Gtk.RadioButton.new_with_label_from_widget(self.as_files, "Archiv tar.zst (kompakt, schneller)")
        store_box.pack_start(self.as_files, False, False, 0)
        store_box.pack_start(self.as_tar, False, False, 0)
        box.pack_start(store_box, False, False, 0)

        note_box = Gtk.Box(spacing=12)
        note_box.pack_start(Gtk.Label(label="Notiz:"), False, False, 0)
        self.note = Gtk.Entry(placeholder_text="optional, z. B. „vor Neuinstallation“ oder Ticketnummer")
        note_box.pack_start(self.note, True, True, 0)
        box.pack_start(note_box, False, False, 0)

        est = Gtk.Box(spacing=8)
        self.btn_estimate = Gtk.Button(label="Grösse berechnen")
        self.btn_estimate.connect("clicked", lambda _b: self._estimate())
        est.pack_start(self.btn_estimate, False, False, 0)
        self.estimate_label = Gtk.Label(xalign=0, wrap=True)
        est.pack_start(self.estimate_label, True, True, 0)
        box.pack_start(est, False, False, 0)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup("<small>Übersprungen werden Auslagerungs- und Ruhezustandsdatei, Papierkorb, Temp-Ordner und "
                        "Caches. Partitionen werden nur lesend eingehängt – am Gerät ändert sich nichts.</small>")
        hint.get_style_context().add_class("status-idle")
        box.pack_start(hint, False, False, 0)
        self.status = Gtk.Label(label="Lese Partitionen und Benutzer vom Agent …", xalign=0, wrap=True)
        self.status.get_style_context().add_class("status-idle")
        box.pack_start(self.status, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()
        _bg(lambda: backups.get_profiles(agent.ip, self.key, agent.control_port), self._on_profiles)

    # ---------- Aufbau ----------

    def _build_profiles(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        # aktiv, Text, Partition (Gerät), Benutzerpfad, Art (windows/linux/home), Zeilenart (part/user)
        self.p_store = Gtk.TreeStore(bool, str, str, str, str, str)
        view = Gtk.TreeView(model=self.p_store, headers_visible=False)
        _check_column(view, self.p_store, 0, self._toggle_profile)
        view.append_column(Gtk.TreeViewColumn("Benutzer", Gtk.CellRendererText(), text=1))
        box.pack_start(scrolled(view), True, True, 0)
        self.p_view = view
        cats = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, column_spacing=12)
        self.categories: dict[str, Gtk.CheckButton] = {}
        for key, (label, _paths) in backups.WINDOWS_CATEGORIES.items():
            cb = Gtk.CheckButton(label=label, active=key in backups.DEFAULT_CATEGORIES)
            cb.connect("toggled", lambda _c: self._update())
            self.categories[key] = cb
            cats.add(cb)
        frame = Gtk.Frame(label="Bei Windows-Benutzern sichern")
        frame.add(cats)
        box.pack_start(frame, False, False, 0)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_markup("<small>Linux-Benutzer: ganzer persönlicher Ordner (ohne Caches).</small>")
        note.get_style_context().add_class("status-idle")
        box.pack_start(note, False, False, 0)
        return box

    def _build_partitions(self) -> Gtk.Widget:
        # aktiv, Partition, Dateisystem, Grösse, System/Label, Gerät
        self.part_store = Gtk.ListStore(bool, str, str, str, str, str)
        view = Gtk.TreeView(model=self.part_store)
        _check_column(view, self.part_store, 0, self._toggle_partition)
        for i, title in ((1, "Partition"), (2, "Dateisystem"), (3, "Grösse"), (4, "Inhalt")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=i)
            col.set_expand(i == 4)
            view.append_column(col)
        return scrolled(view)

    def _build_folders(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin=6)
        # aktiv, Name, Partition (Gerät), Pfad, Ordner?, Grösse
        self.f_store = Gtk.TreeStore(bool, str, str, str, bool, str)
        view = Gtk.TreeView(model=self.f_store)
        _check_column(view, self.f_store, 0, self._toggle_folder)
        icon = Gtk.CellRendererPixbuf()
        col = Gtk.TreeViewColumn("Ordner / Datei")
        col.pack_start(icon, False)
        col.set_cell_data_func(icon, lambda c, cell, m, it, d: cell.set_property(
            "icon-name", "folder-symbolic" if m[it][4] else "text-x-generic-symbolic"))
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(text, True)
        col.add_attribute(text, "text", 1)
        col.set_expand(True)
        view.append_column(col)
        view.append_column(Gtk.TreeViewColumn("Grösse", Gtk.CellRendererText(), text=5))
        view.connect("row-expanded", self._on_expand)
        box.pack_start(scrolled(view), True, True, 0)
        note = Gtk.Label(label="Aufklappen lädt den Inhalt vom Gerät. Ein angehakter Ordner wird mit Inhalt gesichert.",
                         xalign=0, wrap=True)
        note.get_style_context().add_class("status-idle")
        box.pack_start(note, False, False, 0)
        return box

    # ---------- Daten ----------

    def _on_profiles(self, result) -> bool:
        if isinstance(result, Exception):
            self.status.set_text(f"Agent nicht erreichbar: {result}")
            return False
        self.partitions = result
        self.status.set_text("")
        for p in result:
            label = f"{p['name']}  {p['fstype']}  {nas.format_size(p['size'])}" + \
                    (f"  – {p['os']}" if p.get("os") else (f"  „{p['label']}“" if p.get("label") else ""))
            if p.get("users"):
                it = self.p_store.append(None, [True, label, p["part"], "", p["kind"], "part"])
                for u in p["users"]:
                    self.p_store.append(it, [True, u["name"], p["part"], u["path"], p["kind"], "user"])
            self.part_store.append([False, p["name"], p["fstype"], nas.format_size(p["size"]),
                                    p.get("error") or p.get("os") or p.get("label") or "", p["part"]])
            if not p.get("error"):
                it = self.f_store.append(None, [False, f"{p['name']} ({p.get('os') or p['fstype']})", p["part"], "",
                                                True, nas.format_size(p["size"])])
                self.f_store.append(it, [False, PLACEHOLDER, "", "", False, ""])
        self.p_view.expand_all()
        if not any(p.get("users") for p in result):
            self.tabs.set_current_page(1)
        self._update()
        return False

    def _on_expand(self, view, it, path) -> None:
        child = self.f_store.iter_children(it)
        if child is None or self.f_store[child][1] != PLACEHOLDER:
            return
        part, rel, checked = self.f_store[it][2], self.f_store[it][3], self.f_store[it][0]
        ref = Gtk.TreeRowReference.new(self.f_store, path)

        def done(result) -> bool:
            if not ref.valid():
                return False
            parent = self.f_store.get_iter(ref.get_path())
            first = self.f_store.iter_children(parent)
            if isinstance(result, Exception):
                self.f_store[first][1] = f"nicht lesbar: {result}"
                return False
            for e in result:
                sub = f"{rel}/{e['name']}" if rel else e["name"]
                c = self.f_store.append(parent, [checked, e["name"], part, sub, e["dir"],
                                                 "" if e["dir"] else nas.format_size(e["size"])])
                if e["dir"]:
                    self.f_store.append(c, [False, PLACEHOLDER, "", "", False, ""])
            self.f_store.remove(first)
            view.expand_row(ref.get_path(), False)
            return False

        _bg(lambda: backups.browse(self.agent.ip, self.key, self.agent.control_port, part, rel), done)

    def _toggle_profile(self, _cell, path) -> None:
        it = self.p_store.get_iter(path)
        value = not self.p_store[it][0]
        self.p_store[it][0] = value
        _set_children(self.p_store, it, 0, value)
        self._update()

    def _toggle_partition(self, _cell, path) -> None:
        self.part_store[path][0] = not self.part_store[path][0]
        self._update()

    def _toggle_folder(self, _cell, path) -> None:
        it = self.f_store.get_iter(path)
        if self.f_store[it][1] == PLACEHOLDER:
            return
        value = not self.f_store[it][0]
        self.f_store[it][0] = value
        _set_children(self.f_store, it, 0, value)
        self._update()

    # ---------- Auswahl ----------

    def mode(self) -> str:
        return ("profiles", "partitions", "folders")[self.tabs.get_current_page()]

    def selection(self) -> tuple[list[dict], list[str]]:
        """(Quellen für den Agent, Beschreibung)."""
        mode = self.mode()
        sources, names = [], []
        if mode == "profiles":
            cats = [k for k, cb in self.categories.items() if cb.get_active()]
            for row in self.p_store:
                for u in row.iterchildren():
                    if u[0]:
                        sources += backups.profile_sources(u[2], u[3], u[4], cats)
                        names.append(f"{u[1]} ({Path(u[2]).name})")
            names.append("Kategorien: " + ", ".join(backups.WINDOWS_CATEGORIES[c][0] for c in cats))
        elif mode == "partitions":
            for row in self.part_store:
                if row[0]:
                    sources.append({"part": row[5], "path": ""})
                    names.append(row[1])
        else:
            def walk(it, parent_checked: bool):
                while it is not None:
                    row = self.f_store[it]
                    if row[1] != PLACEHOLDER:
                        if row[0] and not parent_checked:
                            sources.append({"part": row[2], "path": row[3]})
                            names.append(f"{Path(row[2]).name}/{row[3]}" if row[3] else Path(row[2]).name)
                        walk(self.f_store.iter_children(it), parent_checked or row[0])
                    it = self.f_store.iter_next(it)
            walk(self.f_store.get_iter_first(), False)
        storage = "files" if self.as_files.get_active() else "tar"
        return sources, backups.describe_selection(mode, names, storage)

    def _disk(self, sources: list[dict]) -> str:
        parts = {p["part"]: p["disk"] for p in self.partitions}
        return parts.get(sources[0]["part"], "") if sources else ""

    def _update(self) -> bool:
        sources, _desc = self.selection()
        self.btn_start.set_sensitive(bool(sources))
        self.btn_estimate.set_sensitive(bool(sources))
        self.estimate_label.set_text("")
        return False

    def _estimate(self) -> None:
        sources, _desc = self.selection()
        self.btn_estimate.set_sensitive(False)
        self.estimate_label.set_text("Zähle Dateien auf dem Gerät …")
        _bg(lambda: backups.estimate(self.agent.ip, self.key, self.agent.control_port, sources), self._on_estimate)

    def _on_estimate(self, result) -> bool:
        self.btn_estimate.set_sensitive(True)
        if isinstance(result, Exception):
            self.estimate_label.set_text(f"Fehler: {result}")
            return False
        try:
            free = shutil.disk_usage(self.nas_root).free
        except OSError:
            free = 0
        text = f"{result['files']} Dateien, {nas.format_size(result['bytes'])}"
        if result.get("skipped"):
            text += f" ({result['skipped']} nicht lesbar)"
        if free and result["bytes"] > free:
            self.estimate_label.set_markup(f"<b>{GLib.markup_escape_text(text)} – mehr als frei auf dem NAS "
                                           f"({nas.format_size(free)})</b>")
        else:
            self.estimate_label.set_text(text + (f" · NAS frei: {nas.format_size(free)}" if free else ""))
        return False

    def _on_response(self, _dlg, response: int) -> None:
        if response != Gtk.ResponseType.APPLY:
            self.destroy()
            return
        sources, desc = self.selection()
        try:
            self.start_job(self._disk(sources), sources, self.mode(), "files" if self.as_files.get_active() else "tar",
                           desc, self.note.get_text().strip())
        except Exception as e:
            self.status.set_text(f"Nicht gestartet: {e}")
            return
        self.destroy()


class RestoreFilesDialog(Gtk.Dialog):
    """Backup zurückspielen: ins installierte System (über den Agent) oder herunterladen.

    start_restore(disk, plan) wird nur angeboten, wenn agent gesetzt ist; start_download(ziel, präfixe)."""

    def __init__(self, parent: Gtk.Window, backup: backups.BackupInfo, agent, device_name: str,
                 start_restore, start_download):
        super().__init__(title="Backup zurückspielen", transient_for=parent, modal=True)
        self.set_default_size(820, 720)
        self.backup, self.agent = backup, agent
        self.start_restore, self.start_download = start_restore, start_download
        self.key = agentclient.load_or_create_key()
        self.targets: list[dict] = []
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Starten", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("suggested-action")
        self.connect("response", self._on_response)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        m = backup.manifest
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{GLib.markup_escape_text(backup.device)} – {backup.created:%d.%m.%Y %H:%M}</b>  "
                        f"({nas.format_size(backup.size)})\n<small>{GLib.markup_escape_text(backup.summary)}"
                        + "".join(f"\n{GLib.markup_escape_text(d)}" for d in m.get("description", [])) + "</small>")
        box.pack_start(head, False, False, 0)

        # Was: oberste Ebenen des Backups (Partition, bei Benutzerdaten die Benutzerordner)
        box.pack_start(Gtk.Label(label="Was zurückspielen", xalign=0), False, False, 0)
        self.sel_store = Gtk.ListStore(bool, str, str)  # aktiv, Anzeige, Präfix
        view = Gtk.TreeView(model=self.sel_store, headers_visible=False)
        _check_column(view, self.sel_store, 0, self._toggle_sel)
        view.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=1))
        sw = scrolled(view)
        sw.set_min_content_height(110)
        sw.set_vexpand(True)
        box.pack_start(sw, True, True, 0)
        for prefix, count, size in self._groups():
            self.sel_store.append([True, f"{prefix}  ({count} Dateien, {nas.format_size(size)})", prefix])

        # Wohin
        self.to_system = Gtk.RadioButton.new_with_label(
            None, f"Ins installierte System von „{device_name}“" if agent else "Ins installierte System "
            "(Gerät nicht verbunden)")
        self.to_system.set_sensitive(agent is not None)
        self.to_folder = Gtk.RadioButton.new_with_label_from_widget(self.to_system, "Herunterladen in einen Ordner")
        if agent is None:
            self.to_folder.set_active(True)
        for w in (self.to_system, self.to_folder):
            w.connect("toggled", lambda _w: self._update())
            box.pack_start(w, False, False, 0)

        self.sys_box = Gtk.Grid(column_spacing=8, row_spacing=6, margin_start=24)
        self.sys_box.attach(Gtk.Label(label="Zielpartition", xalign=0), 0, 0, 1, 1)
        self.target_combo = Gtk.ComboBoxText(hexpand=True)
        self.target_combo.connect("changed", lambda _c: self._on_target())
        self.sys_box.attach(self.target_combo, 1, 0, 1, 1)
        self.map_grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        self.sys_box.attach(self.map_grid, 0, 1, 2, 1)
        self.overwrite = Gtk.CheckButton(label="Vorhandene Dateien überschreiben (sonst Kopie mit Zusatz "
                                               "„wiederhergestellt“)")
        self.sys_box.attach(self.overwrite, 0, 2, 2, 1)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_markup("<small>Windows-Partitionen werden schreibend eingehängt – Windows muss vollständig "
                        "heruntergefahren sein (Shift + Herunterfahren, ohne Schnellstart).</small>")
        note.get_style_context().add_class("status-idle")
        self.sys_box.attach(note, 0, 3, 2, 1)
        box.pack_start(self.sys_box, False, False, 0)

        self.folder_box = Gtk.Box(spacing=8, margin_start=24)
        self.folder_box.pack_start(Gtk.Label(label="Ordner"), False, False, 0)
        self.folder = Gtk.FileChooserButton(title="Zielordner wählen", action=Gtk.FileChooserAction.SELECT_FOLDER)
        self.folder.set_filename(str(Path.home()))
        self.folder.set_hexpand(True)
        self.folder_box.pack_start(self.folder, True, True, 0)
        box.pack_start(self.folder_box, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.status, False, False, 0)
        self.get_content_area().pack_start(box, True, True, 0)
        self.show_all()
        self.map_combos: list[tuple[str, Gtk.ComboBoxText, Gtk.Entry | None]] = []
        if agent is not None:
            self.status.set_text("Lese Partitionen und Benutzer des Geräts …")
            _bg(lambda: backups.get_profiles(agent.ip, self.key, agent.control_port), self._on_targets)
        self._update()

    def _groups(self) -> list[tuple[str, int, int]]:
        """Präfixe: Benutzerordner (Windows Users/X, Linux home/X) bzw. Partitionen."""
        groups: dict[str, list[int]] = {}
        for rel, size, _mtime, _sha in backups.read_index(self.backup.path):
            parts = rel.split("/")
            if len(parts) >= 3 and parts[1].lower() in ("users", "home"):
                key = "/".join(parts[:3])
            else:
                key = parts[0]
            g = groups.setdefault(key, [0, 0])
            g[0] += 1
            g[1] += size
        return [(k, v[0], v[1]) for k, v in sorted(groups.items())]

    def _toggle_sel(self, _cell, path) -> None:
        self.sel_store[path][0] = not self.sel_store[path][0]
        self._update()

    def _prefixes(self) -> list[str]:
        return [row[2] for row in self.sel_store if row[0]]

    def _on_targets(self, result) -> bool:
        if isinstance(result, Exception):
            self.status.set_text(f"Agent nicht erreichbar: {result}")
            return False
        self.status.set_text("")
        self.targets = [p for p in result if not p.get("error")]
        for p in self.targets:
            self.target_combo.append(p["part"], f"{p['name']} – {p.get('os') or p['fstype']} "
                                                 f"({nas.format_size(p['size'])})")
        best = next((p for p in self.targets if p.get("users")), self.targets[0] if self.targets else None)
        if best:
            self.target_combo.set_active_id(best["part"])
        return False

    def _on_target(self) -> None:
        for child in self.map_grid.get_children():
            self.map_grid.remove(child)
        self.map_combos = []
        target = next((p for p in self.targets if p["part"] == self.target_combo.get_active_id()), None)
        users = target.get("users", []) if target else []
        for i, (prefix, count, _size) in enumerate(self._groups()):
            self.map_grid.attach(Gtk.Label(label=prefix, xalign=0), 0, i, 1, 1)
            combo = Gtk.ComboBoxText()
            for u in users:
                combo.append(f"user:{u['path']}", f"→ Benutzer {u['name']}")
            combo.append("folder", f"→ Ordner /{backups.RESTORE_DIR}/…")
            combo.append("same", "→ gleicher Pfad wie im Backup")
            name = prefix.rsplit("/", 1)[-1]
            same = next((u for u in users if u["name"].lower() == name.lower()), None)
            is_user = "/" in prefix
            combo.set_active_id(f"user:{same['path']}" if same and is_user else
                                (f"user:{users[0]['path']}" if users and is_user else "folder"))
            self.map_grid.attach(combo, 1, i, 1, 1)
            self.map_combos.append((prefix, combo, None))
        self.map_grid.show_all()
        self._update()

    def plan(self) -> backups.RestorePlan:
        mapping = []
        stamp = self.backup.name
        for prefix, combo, _e in self.map_combos:
            if prefix not in self._prefixes():
                continue
            choice = combo.get_active_id() or "folder"
            if choice.startswith("user:"):
                mapping.append((prefix, choice[5:]))
            elif choice == "same":
                mapping.append((prefix, prefix.split("/", 1)[1] if "/" in prefix else ""))
            else:
                mapping.append((prefix, f"{backups.RESTORE_DIR}/{stamp}/{prefix}"))
        target = next((p for p in self.targets if p["part"] == self.target_combo.get_active_id()), {})
        owner = ""
        if target.get("kind") == "linux":
            owner = next((c[5:].rsplit("/", 1)[-1] for _p, cb, _e in self.map_combos
                          if (c := cb.get_active_id() or "").startswith("user:")), "")
        return backups.RestorePlan(target.get("part", ""), mapping, owner, self.overwrite.get_active(),
                                   self._prefixes())

    def _update(self) -> None:
        system = self.to_system.get_active()
        self.sys_box.set_visible(system)
        self.folder_box.set_visible(not system)
        ok = bool(self._prefixes()) and (not system or bool(self.target_combo.get_active_id()))
        self.btn_start.set_sensitive(ok)
        self.btn_start.set_label("Zurückspielen" if system else "Herunterladen")

    def _on_response(self, _dlg, response: int) -> None:
        if response != Gtk.ResponseType.APPLY:
            self.destroy()
            return
        try:
            if self.to_system.get_active():
                target = next(p for p in self.targets if p["part"] == self.target_combo.get_active_id())
                self.start_restore(target["disk"], self.plan())
            else:
                dest = Path(self.folder.get_filename() or str(Path.home())) / \
                    f"{self.backup.device}_{self.backup.name}"
                self.start_download(str(dest), self._prefixes())
        except Exception as e:
            self.status.set_text(f"Nicht gestartet: {e}")
            return
        self.destroy()


class BackupDetailsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, backup: backups.BackupInfo):
        super().__init__(title=f"Backup – {backup.device} {backup.name}", transient_for=parent, modal=False)
        self.set_default_size(760, 560)
        self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_a: self.destroy())
        m = backup.manifest
        lines = [f"Gerät: {backup.device}", f"Erstellt: {backup.created:%d.%m.%Y %H:%M}", backup.summary,
                 f"Grösse: {nas.format_size(backup.size)}", f"Ordner: {backup.path}", ""]
        if backup.note:
            lines += ["Notiz:"] + [f"  {line}" for line in backup.note.splitlines()] + [""]
        lines += m.get("description", [])
        if m.get("skipped_count"):
            lines += ["", f"Übersprungen bzw. nicht lesbar: {m['skipped_count']}"] + \
                [f"  {s.get('path')}: {s.get('reason')}" for s in m.get("skipped", [])[:200]]
        view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text("\n".join(lines) + "\n\nQuellen:\n" + json.dumps(m.get("sources", []), indent=1,
                                                                                    ensure_ascii=False))
        self.get_content_area().pack_start(scrolled(view), True, True, 0)
        self.show_all()


def edit_note(parent: Gtk.Window, backup: backups.BackupInfo) -> str | None:
    """Notiz bearbeiten; None = abgebrochen."""
    dlg = Gtk.Dialog(title=f"Notiz – {backup.device} {backup.created:%d.%m.%Y %H:%M}", transient_for=parent,
                     modal=True)
    dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Speichern", Gtk.ResponseType.OK)
    dlg.set_default_size(520, 280)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
    box.pack_start(Gtk.Label(label="Notiz zum Backup (wird beim Backup auf dem NAS gespeichert):", xalign=0),
                   False, False, 0)
    view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    buf = view.get_buffer()
    buf.set_text(backup.note)
    box.pack_start(scrolled(view), True, True, 0)
    dlg.get_content_area().pack_start(box, True, True, 0)
    dlg.show_all()
    view.grab_focus()
    text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) if dlg.run() == Gtk.ResponseType.OK else None
    dlg.destroy()
    return text
