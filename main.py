"""GrabQueue — a persistent, resumable download queue built on yt-dlp.

The queue survives restarts, failed items auto-retry with backoff, engines
(yt-dlp + FFmpeg) are bundled and self-updating. No subscription, no ads.
"""
import json
import os
import subprocess
import sys
import webbrowser

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QProgressBar,
    QComboBox, QSpinBox, QFileDialog, QDialog, QFormLayout, QMenu,
    QMessageBox, QCheckBox, QHeaderView)

import engines
import store as st
import theme
from downloader import (DownloadManager, PRESETS, DEFAULT_PRESET,
                        GALLERY_PRESET)
from store import QueueStore

APP_DIR = engines.APP_DIR
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
DB_PATH = os.path.join(APP_DIR, "grabqueue.db")

# Shared hand-off file: other apps (e.g. Image Downloader) drop URLs here and
# GrabQueue imports them. Lives in LOCALAPPDATA so it's found no matter where
# either app is installed.
INBOX_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "GrabQueue", "inbox.txt")

# GrabQueue is free — donations keep it maintained.
DONATE_URL = "https://paypal.me/gamer4life33"


def read_inbox():
    """Atomically claim any URLs waiting in the shared inbox and return them.

    Renames the file to a unique name first (atomic on Windows) so neither a
    producer appending concurrently nor a second GrabQueue instance can lose or
    double-import a line: only one caller can win the rename of the current
    inbox; everyone else gets 'file not found' and returns nothing.
    """
    import uuid
    if not os.path.exists(INBOX_PATH):
        return []
    claimed = f"{INBOX_PATH}.{uuid.uuid4().hex}.importing"
    try:
        os.replace(INBOX_PATH, claimed)
    except OSError:
        return []
    try:
        with open(claimed, encoding="utf-8") as f:
            urls = [ln.strip() for ln in f if ln.strip()]
    except OSError:
        urls = []
    finally:
        try:
            os.remove(claimed)
        except OSError:
            pass
    return urls

DISCLAIMER = """\
GrabQueue is a free download-queue manager provided for entertainment and \
personal convenience. By using it you agree to the following:

1. SOLE RESPONSIBILITY — You alone are responsible for how you use this \
software and for any content you download with it.

2. RESPECT THE LAW — Only download content you have the legal right to \
access and save. Do not use GrabQueue to infringe copyright, bypass \
paywalls, or circumvent DRM / technical protection measures. GrabQueue \
contains no circumvention technology and never will.

3. TERMS OF SERVICE — Downloading from a website may violate that site's \
terms of service. Know the rules of the sites you use; any consequences \
(including account restrictions) are yours.

4. PERSONAL USE — Content you download is for your own personal, \
non-commercial use unless the rights holder permits otherwise. Do not \
redistribute downloaded content.

5. THIRD-PARTY ENGINES — Downloads are performed by independent \
open-source projects (yt-dlp, gallery-dl, FFmpeg) fetched from their \
official sources and governed by their own licenses. GrabQueue is not \
affiliated with, or endorsed by, those projects or by any website.

6. NO WARRANTY — This software is provided "AS IS", without warranty of \
any kind. The author is not liable for any damages arising from its use.

7. NOT LEGAL ADVICE — Nothing in this application constitutes legal advice.

If you do not agree with these terms, do not use GrabQueue."""


def _center_on_primary(widget):
    """Move a top-level widget to the center of the primary screen.

    A parentless dialog otherwise lands on whatever screen Qt treats as
    primary, which on a multi-monitor setup may not be the one in front of
    the user — the disclaimer must always be visible.
    """
    screen = QApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    frame = widget.frameGeometry()
    frame.moveCenter(geo.center())
    widget.move(frame.topLeft())


class DisclaimerDialog(QDialog):
    def __init__(self, parent=None, first_run=False):
        super().__init__(parent)
        self.setWindowTitle("GrabQueue — Legal Disclaimer")
        self.resize(560, 520)
        self.setModal(True)
        layout = QVBoxLayout(self)
        title = QLabel("Before you start")
        title.setObjectName("title")
        layout.addWidget(title)
        from PySide6.QtWidgets import QPlainTextEdit
        text = QPlainTextEdit(DISCLAIMER)
        text.setReadOnly(True)
        layout.addWidget(text, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        if first_run:
            decline = QPushButton("Decline")
            decline.clicked.connect(self.reject)
            accept = QPushButton("I Agree")
            accept.setObjectName("accent")
            accept.clicked.connect(self.accept)
            buttons.addWidget(decline)
            buttons.addWidget(accept)
        else:
            close = QPushButton("Close")
            close.clicked.connect(self.accept)
            buttons.addWidget(close)
        layout.addLayout(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        _center_on_primary(self)
        self.raise_()
        self.activateWindow()

DEFAULT_SETTINGS = {
    "output_dir": os.path.join(os.path.expanduser("~"), "Downloads", "GrabQueue"),
    "preset": DEFAULT_PRESET,
    "concurrency": 2,
    "cookies_browser": "",
    "auto_start": True,
    "expand_playlists": True,
}

STATUS_LABEL = {
    st.QUEUED: "Queued", st.FETCHING: "Starting…", st.DOWNLOADING: "Downloading",
    st.CONVERTING: "Converting", st.DONE: "✓ Done", st.FAILED: "✗ Failed",
    st.CANCELED: "Canceled", st.PAUSED: "Paused",
}
STATUS_COLOR = {
    st.DONE: theme.OK, st.FAILED: theme.ERR, st.CANCELED: theme.MUTED,
    st.DOWNLOADING: theme.ACCENT_HI, st.CONVERTING: theme.WARN,
}


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


class ExpandThread(QThread):
    """Resolve a URL into its playlist entries (or itself) via yt-dlp."""
    resolved = Signal(str, list)   # original url, [(entry_url, title), ...]

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        entries = []
        try:
            out = subprocess.run(
                [engines.YTDLP_EXE, "--flat-playlist", "--no-warnings",
                 "--print", "%(url)s\t%(title)s", self.url],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180,
                creationflags=engines.NO_WINDOW)
            for line in out.stdout.splitlines():
                if "\t" in line:
                    entry_url, title = line.split("\t", 1)
                    if entry_url.startswith("http"):
                        entries.append(
                            (entry_url, "" if title == "NA" else title))
        except Exception:
            pass
        self.resolved.emit(self.url, entries)


class EngineSetupThread(QThread):
    progress = Signal(str, float)
    done = Signal(str)   # error text or ""

    def run(self):
        try:
            engines.ensure_engines(lambda label, frac:
                                   self.progress.emit(label, frac))
            self.done.emit("")
        except Exception as e:
            self.done.emit(str(e))


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        form = QFormLayout(self)

        row = QHBoxLayout()
        self.out_edit = QLineEdit(settings["output_dir"])
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_folder)
        row.addWidget(self.out_edit)
        row.addWidget(browse)
        form.addRow("Save to", row)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS.keys())
        self.preset_combo.setCurrentText(settings["preset"])
        form.addRow("Default quality", self.preset_combo)

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 8)
        self.conc_spin.setValue(int(settings["concurrency"]))
        form.addRow("Parallel downloads", self.conc_spin)

        self.cookies_combo = QComboBox()
        self.cookies_combo.addItems(
            ["(none)", "chrome", "edge", "firefox", "opera", "brave", "vivaldi"])
        self.cookies_combo.setCurrentText(settings["cookies_browser"] or "(none)")
        form.addRow("Use browser cookies", self.cookies_combo)
        hint = QLabel("Needed for age-restricted / members-only videos and\n"
                      "sites that show \"confirm you're not a bot\" errors.")
        hint.setObjectName("muted")
        form.addRow("", hint)

        self.autostart_check = QCheckBox("Start downloading as soon as URLs are added")
        self.autostart_check.setChecked(bool(settings["auto_start"]))
        form.addRow("", self.autostart_check)

        self.expand_check = QCheckBox("Expand playlists into individual queue items")
        self.expand_check.setChecked(bool(settings.get("expand_playlists", True)))
        form.addRow("", self.expand_check)

        buttons = QHBoxLayout()
        ok = QPushButton("Save")
        ok.setObjectName("accent")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        form.addRow(buttons)

    def _pick_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose download folder",
                                                  self.out_edit.text())
        if chosen:
            self.out_edit.setText(chosen)

    def result_settings(self):
        browser = self.cookies_combo.currentText()
        return {
            "output_dir": self.out_edit.text().strip() or DEFAULT_SETTINGS["output_dir"],
            "preset": self.preset_combo.currentText(),
            "concurrency": self.conc_spin.value(),
            "cookies_browser": "" if browser == "(none)" else browser,
            "auto_start": self.autostart_check.isChecked(),
            "expand_playlists": self.expand_check.isChecked(),
        }


COL_TITLE, COL_STATUS, COL_PROGRESS, COL_SIZE, COL_SPEED, COL_ETA = range(6)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GrabQueue")
        self.resize(980, 640)
        self.settings = load_settings()

        self.store = QueueStore(DB_PATH)
        self.store.reset_interrupted()
        self.manager = DownloadManager(self.store, self.settings)
        self.manager.item_changed.connect(self._on_item_changed)

        self._rows = {}          # item_id -> table row
        self._build_ui()
        self._reload_table()
        self._setup_engines()

        # Import anything waiting in the shared inbox now, then keep watching.
        self._import_inbox()
        self._inbox_timer = QTimer(self)
        self._inbox_timer.timeout.connect(self._import_inbox)
        self._inbox_timer.start(3000)

    # ---- UI construction --------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("GrabQueue")
        title.setObjectName("title")
        header.addWidget(title)
        sub = QLabel("paste a link — it downloads, retries, and survives restarts")
        sub.setObjectName("muted")
        header.addWidget(sub)
        header.addStretch()
        donate_btn = QPushButton("💛 Donate")
        donate_btn.setToolTip("GrabQueue is free — buy me a coffee via PayPal")
        donate_btn.clicked.connect(lambda: webbrowser.open(DONATE_URL))
        header.addWidget(donate_btn)
        root.addLayout(header)

        add_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "Paste video / playlist URLs here (space or newline separated)…")
        self.url_edit.returnPressed.connect(self._add_urls)
        add_btn = QPushButton("Add to queue")
        add_btn.setObjectName("accent")
        add_btn.clicked.connect(self._add_urls)
        paste_btn = QPushButton("📋 Paste && add")
        paste_btn.clicked.connect(self._paste_add)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS.keys())
        self.preset_combo.setCurrentText(self.settings["preset"])
        add_row.addWidget(self.url_edit, 1)
        add_row.addWidget(self.preset_combo)
        add_row.addWidget(add_btn)
        add_row.addWidget(paste_btn)
        root.addLayout(add_row)

        control_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start queue")
        self.start_btn.clicked.connect(self._toggle_running)
        retry_btn = QPushButton("Retry failed")
        retry_btn.clicked.connect(self._retry_failed)
        clear_btn = QPushButton("Clear finished")
        clear_btn.clicked.connect(self._clear_finished)
        folder_btn = QPushButton("Open folder")
        folder_btn.clicked.connect(self._open_folder)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        legal_btn = QPushButton("Legal")
        legal_btn.clicked.connect(
            lambda: DisclaimerDialog(self, first_run=False).exec())
        control_row.addWidget(self.start_btn)
        control_row.addWidget(retry_btn)
        control_row.addWidget(clear_btn)
        control_row.addStretch()
        control_row.addWidget(folder_btn)
        control_row.addWidget(settings_btn)
        control_row.addWidget(legal_btn)
        root.addLayout(control_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Title", "Status", "Progress", "Size", "Speed", "ETA"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        self.table.setColumnWidth(COL_TITLE, 380)
        self.table.setColumnWidth(COL_STATUS, 110)
        self.table.setColumnWidth(COL_PROGRESS, 160)
        self.table.setColumnWidth(COL_SIZE, 90)
        self.table.setColumnWidth(COL_SPEED, 100)
        self.table.setColumnWidth(COL_ETA, 70)
        hdr.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.status_engines = QLabel("checking engines…")
        self.statusBar().addWidget(self.status_engines)
        self.status_counts = QLabel("")
        self.statusBar().addPermanentWidget(self.status_counts)

        self._counts_timer = QTimer(self)
        self._counts_timer.timeout.connect(self._refresh_counts)
        self._counts_timer.start(1000)

    # ---- engines bootstrap -------------------------------------------------
    def _setup_engines(self):
        if engines.engines_ready():
            self._engines_ok()
            return
        self.start_btn.setEnabled(False)
        self.status_engines.setText("Downloading engines (first run)…")
        self._setup_thread = EngineSetupThread()
        self._setup_thread.progress.connect(
            lambda label, frac: self.status_engines.setText(
                f"Downloading {label}… {frac:.0%}"))
        self._setup_thread.done.connect(self._engines_done)
        self._setup_thread.start()

    def _engines_done(self, error):
        if error:
            self.status_engines.setText(f"Engine setup failed: {error}")
            QMessageBox.warning(self, "GrabQueue",
                                f"Could not download engines:\n{error}\n\n"
                                "Check your connection and restart the app.")
            return
        self._engines_ok()

    def _engines_ok(self):
        version = engines.ytdlp_version()
        self.status_engines.setText(f"yt-dlp {version or '?'} · FFmpeg bundled")
        self.start_btn.setEnabled(True)
        if self.settings.get("auto_start") and self.store.count(st.QUEUED):
            self._set_running(True)
        # check for engine updates in the background shortly after launch
        QTimer.singleShot(3000, self._update_engines_async)

    def _update_engines_async(self):
        class _Upd(QThread):
            done = Signal(str)

            def run(self):
                self.done.emit(engines.update_ytdlp())

        self._upd_thread = _Upd()
        self._upd_thread.done.connect(self._on_engine_updated)
        self._upd_thread.start()

    def _on_engine_updated(self, output):
        version = engines.ytdlp_version()
        note = "up to date" if "is up to date" in output else "updated"
        self.status_engines.setText(
            f"yt-dlp {version or '?'} ({note}) · FFmpeg bundled")

    # ---- queue actions -----------------------------------------------------
    def _add_urls(self):
        text = self.url_edit.text().strip()
        if not text:
            return
        urls = [u for u in text.replace("\n", " ").split(" ") if u.strip()]
        preset = self.preset_combo.currentText()
        outdir = self.settings["output_dir"]
        expand = (self.settings.get("expand_playlists", True)
                  and engines.engines_ready())
        for url in urls:
            if preset == GALLERY_PRESET:
                item_id = self.store.add(url, preset, outdir, engine="gallery")
                self._append_row(self.store.get(item_id))
            elif expand:
                self._start_expand(url, preset, outdir)
            else:
                item_id = self.store.add(url, preset, outdir)
                self._append_row(self.store.get(item_id))
        self.url_edit.clear()
        if self.settings.get("auto_start") and engines.engines_ready():
            self._set_running(True)

    def _start_expand(self, url, preset, outdir):
        self._pending_expands = getattr(self, "_pending_expands", 0) + 1
        self.statusBar().showMessage(
            f"Resolving {self._pending_expands} link(s)…")
        thread = ExpandThread(url)
        self._expanders = getattr(self, "_expanders", [])
        self._expanders.append(thread)

        def on_resolved(orig_url, entries, preset=preset, outdir=outdir,
                        thread=thread):
            self._pending_expands -= 1
            if self._pending_expands <= 0:
                self.statusBar().clearMessage()
            else:
                self.statusBar().showMessage(
                    f"Resolving {self._pending_expands} link(s)…")
            if not entries:      # resolution failed — queue the raw URL;
                entries = [(orig_url, "")]   # engine fallback handles the rest
            elif len(entries) > 1:
                self.statusBar().showMessage(
                    f"Playlist expanded into {len(entries)} items", 5000)
            for entry_url, title in entries:
                item_id = self.store.add(entry_url, preset, outdir,
                                         title=title)
                self._append_row(self.store.get(item_id))
            self._expanders.remove(thread)

        thread.resolved.connect(on_resolved)
        thread.start()

    def _paste_add(self):
        clip = QApplication.clipboard().text().strip()
        if clip:
            existing = self.url_edit.text().strip()
            self.url_edit.setText((existing + " " + clip).strip())
            self._add_urls()

    def _toggle_running(self):
        self._set_running(not self.manager.running)

    def _set_running(self, run):
        if run:
            self.manager.start()
            self.start_btn.setText("⏸ Pause queue")
        else:
            self.manager.pause()
            self.start_btn.setText("▶ Start queue")

    def _retry_failed(self):
        self.store.requeue_failed()
        self._reload_table()

    def _clear_finished(self):
        self.store.clear_finished()
        self._reload_table()

    def _open_folder(self):
        os.makedirs(self.settings["output_dir"], exist_ok=True)
        os.startfile(self.settings["output_dir"])

    def _open_settings(self):
        dlg = SettingsDialog(dict(self.settings), self)
        if dlg.exec():
            self.settings.update(dlg.result_settings())
            save_settings(self.settings)
            self.manager.settings = self.settings
            self.preset_combo.setCurrentText(self.settings["preset"])

    # ---- table -------------------------------------------------------------
    def _reload_table(self):
        self.table.setRowCount(0)
        self._rows.clear()
        for item in self.store.all_items():
            self._append_row(item)

    def _append_row(self, item):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._rows[item["id"]] = row
        title_item = QTableWidgetItem()
        title_item.setData(Qt.UserRole, item["id"])
        self.table.setItem(row, COL_TITLE, title_item)
        self.table.setItem(row, COL_STATUS, QTableWidgetItem())
        bar = QProgressBar()
        bar.setRange(0, 100)
        self.table.setCellWidget(row, COL_PROGRESS, bar)
        self.table.setItem(row, COL_SIZE, QTableWidgetItem())
        self.table.setItem(row, COL_SPEED, QTableWidgetItem())
        self.table.setItem(row, COL_ETA, QTableWidgetItem())
        self._paint_row(item)

    def _paint_row(self, item):
        row = self._rows.get(item["id"])
        if row is None:
            return
        title = item["title"] or item["url"]
        self.table.item(row, COL_TITLE).setText(title)
        self.table.item(row, COL_TITLE).setToolTip(
            item["url"] + (f"\n\n{item['error']}" if item["error"] else ""))
        status_item = self.table.item(row, COL_STATUS)
        status_item.setText(STATUS_LABEL.get(item["status"], item["status"]))
        color = STATUS_COLOR.get(item["status"])
        status_item.setForeground(QColor(color) if color else QColor(theme.TEXT))
        bar = self.table.cellWidget(row, COL_PROGRESS)
        if bar:
            bar.setValue(int(item["progress"] or 0))
        self.table.item(row, COL_SIZE).setText(item["size"] or "")
        self.table.item(row, COL_SPEED).setText(item["speed"] or "")
        self.table.item(row, COL_ETA).setText(item["eta"] or "")

    def _on_item_changed(self, item_id):
        item = self.store.get(item_id)
        if item:
            self._paint_row(item)

    def _import_inbox(self):
        """Pull any URLs handed over by another app and queue them."""
        urls = read_inbox()
        if not urls:
            return
        outdir = self.settings["output_dir"]
        preset = self.settings["preset"]
        for url in urls:
            item_id = self.store.add(url, preset, outdir)
            self._append_row(self.store.get(item_id))
        self.statusBar().showMessage(
            f"Received {len(urls)} link(s) from another app", 5000)
        if self.settings.get("auto_start") and engines.engines_ready():
            self._set_running(True)

    def _refresh_counts(self):
        done = self.store.count(st.DONE)
        failed = self.store.count(st.FAILED)
        queued = self.store.count(st.QUEUED)
        active = self.store.count(*st.ACTIVE)
        self.status_counts.setText(
            f"{active} active · {queued} queued · {done} done · {failed} failed")

    # ---- context menu -------------------------------------------------------
    def _selected_ids(self):
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), COL_TITLE)
            if item:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _context_menu(self, pos):
        ids = self._selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        act_retry = menu.addAction("Retry")
        act_cancel = menu.addAction("Cancel")
        menu.addSeparator()
        act_open = menu.addAction("Open file")
        act_show = menu.addAction("Show in folder")
        act_copy = menu.addAction("Copy URL")
        menu.addSeparator()
        act_remove = menu.addAction("Remove from list")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_retry:
            for item_id in ids:
                self.manager.retry_item(item_id)
        elif chosen == act_cancel:
            for item_id in ids:
                self.manager.cancel_item(item_id)
        elif chosen == act_open:
            for item_id in ids:
                item = self.store.get(item_id)
                if item and item["file_path"] and os.path.exists(item["file_path"]):
                    os.startfile(item["file_path"])
        elif chosen == act_show:
            for item_id in ids[:1]:
                item = self.store.get(item_id)
                if item and item["file_path"] and os.path.exists(item["file_path"]):
                    os.startfile(os.path.dirname(item["file_path"]))
        elif chosen == act_copy:
            urls = [self.store.get(i)["url"] for i in ids if self.store.get(i)]
            QApplication.clipboard().setText("\n".join(urls))
        elif chosen == act_remove:
            for item_id in ids:
                self.manager.cancel_item(item_id)
            self.store.remove(ids)
            self._reload_table()

    def closeEvent(self, event):
        save_settings(self.settings)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.QSS)
    icon_path = os.path.join(APP_DIR, "grabqueue.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # First run: the disclaimer must be accepted before the app opens.
    settings = load_settings()
    if not settings.get("disclaimer_accepted"):
        dlg = DisclaimerDialog(first_run=True)
        if not dlg.exec():
            sys.exit(0)
        settings["disclaimer_accepted"] = True
        save_settings(settings)

    win = MainWindow()
    win.show()
    _center_on_primary(win)
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
