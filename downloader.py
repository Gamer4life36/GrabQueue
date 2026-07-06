"""Download manager: worker pool around yt-dlp with progress parsing,
automatic retries with backoff, and cancel support.
"""
import os
import re
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal

import engines
import store as st

# Format presets shown in the UI. Order matters (display order).
PRESETS = {
    "Best quality":        ["-f", "bv*+ba/b"],
    "1080p":               ["-S", "res:1080"],
    "720p":                ["-S", "res:720"],
    "Audio only (MP3)":    ["-x", "--audio-format", "mp3"],
    "Audio only (best)":   ["-f", "ba/b", "-x"],
    "Gallery / images":    [],   # handled by the gallery-dl engine
}
DEFAULT_PRESET = "Best quality"
GALLERY_PRESET = "Gallery / images"

_PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<pct>[\d.]+)%\s+of\s+~?\s*(?P<size>[\d.]+\w+)"
    r"(?:\s+at\s+(?P<speed>[^\s]+))?(?:\s+ETA\s+(?P<eta>[^\s]+))?")

MAX_AUTO_RETRIES = 3
RETRY_BACKOFF = 15  # seconds, multiplied by attempt number


class DownloadManager(QObject):
    item_changed = Signal(int)      # item id — row should be re-read from store
    queue_idle = Signal()           # nothing left to do

    def __init__(self, queue_store, settings):
        super().__init__()
        self.store = queue_store
        self.settings = settings     # dict-like: concurrency, cookies_browser
        self.running = False
        self._procs = {}             # item_id -> Popen
        self._threads = {}           # item_id -> Thread
        self._retry_at = {}          # item_id -> monotonic time
        self._lock = threading.Lock()
        self._pump = threading.Thread(target=self._pump_loop, daemon=True)
        self._pump.start()

    # -- public control ----------------------------------------------------
    def start(self):
        self.running = True

    def pause(self):
        """Stop starting new items; running items keep going."""
        self.running = False

    def cancel_item(self, item_id):
        item = self.store.get(item_id)
        if not item or item["status"] in (st.DONE, st.CANCELED):
            return
        # record the cancel first so the finish handler knows it was deliberate
        self.store.update(item_id, status=st.CANCELED, speed="", eta="")
        self._retry_at.pop(item_id, None)
        with self._lock:
            proc = self._procs.get(item_id)
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        self.item_changed.emit(item_id)

    def retry_item(self, item_id):
        self.store.update(item_id, status=st.QUEUED, error="", retries=0)
        self._retry_at.pop(item_id, None)
        self.item_changed.emit(item_id)

    def active_count(self):
        with self._lock:
            return len(self._procs) + len([t for t in self._threads.values()
                                           if t.is_alive()])

    # -- scheduling --------------------------------------------------------
    def _pump_loop(self):
        while True:
            time.sleep(0.5)
            if not self.running or not engines.engines_ready():
                continue
            # release due retries
            now = time.monotonic()
            for item_id, when in list(self._retry_at.items()):
                if now >= when:
                    del self._retry_at[item_id]
                    self.store.update(item_id, status=st.QUEUED)
                    self.item_changed.emit(item_id)
            limit = int(self.settings.get("concurrency", 2))
            while self.active_count() < limit:
                item = self.store.next_queued()
                if not item:
                    if self.active_count() == 0:
                        self.queue_idle.emit()
                    break
                self.store.update(item["id"], status=st.FETCHING,
                                  error="", speed="", eta="")
                self.item_changed.emit(item["id"])
                t = threading.Thread(target=self._run_item, args=(item,),
                                     daemon=True)
                with self._lock:
                    self._threads[item["id"]] = t
                t.start()

    # -- one download ------------------------------------------------------
    @staticmethod
    def _is_gallery(item):
        return (item.get("engine") == "gallery"
                or item.get("preset") == GALLERY_PRESET)

    def _build_cmd(self, item):
        outdir = item["output_dir"]
        browser = self.settings.get("cookies_browser", "")
        if self._is_gallery(item):
            # gallery-dl keeps its own site/album folder structure under outdir
            cmd = [engines.GALLERYDL_EXE, "-d", outdir]
            if browser:
                cmd += ["--cookies-from-browser", browser]
            cmd.append(item["url"])
            return cmd
        cmd = [engines.YTDLP_EXE,
               "--newline", "--no-playlist",
               "--ffmpeg-location", engines.ENGINES_DIR,
               "--no-mtime",
               "--print", "before_dl:GQTITLE\t%(title)s",
               "--print", "after_move:GQPATH\t%(filepath)s",
               "--no-simulate",
               "-o", os.path.join(outdir, "%(title).180B [%(id)s].%(ext)s")]
        cmd += PRESETS.get(item["preset"], PRESETS[DEFAULT_PRESET])
        if browser:
            cmd += ["--cookies-from-browser", browser]
        cmd.append(item["url"])
        return cmd

    def _run_item(self, item):
        item_id = item["id"]
        os.makedirs(item["output_dir"], exist_ok=True)
        try:
            proc = subprocess.Popen(
                self._build_cmd(item),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=engines.NO_WINDOW)
        except Exception as e:
            self._finish_failed(item_id, item, f"could not start yt-dlp: {e}")
            return
        with self._lock:
            self._procs[item_id] = proc

        tail = []
        last_emit = 0.0
        gallery = self._is_gallery(item)
        files_done = 0
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tail.append(line)
                if len(tail) > 12:
                    tail.pop(0)

                if gallery:
                    # gallery-dl prints one path per downloaded file
                    # ("# path" for files that already existed)
                    if not line.startswith(("[", "ERROR", "WARNING")):
                        files_done += 1
                        now = time.monotonic()
                        if now - last_emit > 0.25:
                            last_emit = now
                            self.store.update(item_id, status=st.DOWNLOADING,
                                              size=f"{files_done} file(s)")
                            self.item_changed.emit(item_id)
                    continue

                if line.startswith("GQTITLE\t"):
                    self.store.update(item_id, title=line.split("\t", 1)[1],
                                      status=st.DOWNLOADING)
                    self.item_changed.emit(item_id)
                elif line.startswith("GQPATH\t"):
                    self.store.update(item_id, file_path=line.split("\t", 1)[1])
                elif "[Merger]" in line or "[ExtractAudio]" in line:
                    self.store.update(item_id, status=st.CONVERTING,
                                      speed="", eta="")
                    self.item_changed.emit(item_id)
                else:
                    m = _PROGRESS_RE.search(line)
                    if m:
                        now = time.monotonic()
                        if now - last_emit > 0.25:  # throttle UI updates
                            last_emit = now
                            self.store.update(
                                item_id, status=st.DOWNLOADING,
                                progress=float(m.group("pct")),
                                size=m.group("size") or "",
                                speed=m.group("speed") or "",
                                eta=m.group("eta") or "")
                            self.item_changed.emit(item_id)
            proc.wait()
        finally:
            with self._lock:
                self._procs.pop(item_id, None)
                self._threads.pop(item_id, None)

        current = self.store.get(item_id)
        if current is None:            # removed while downloading
            return
        if current["status"] == st.CANCELED:
            pass                        # user cancel already recorded
        elif proc.returncode == 0:
            fields = dict(status=st.DONE, progress=100.0, speed="", eta="",
                          finished_at=time.time())
            if gallery:
                fields["size"] = f"{files_done} file(s)"
                fields["file_path"] = item["output_dir"]
            self.store.update(item_id, **fields)
            self.item_changed.emit(item_id)
        else:
            error = next((l for l in reversed(tail) if "ERROR" in l),
                         tail[-1] if tail else f"exit code {proc.returncode}")
            # a video URL yt-dlp doesn't know may well be a gallery — hand it
            # to gallery-dl once before giving up
            if (not gallery and "Unsupported URL" in error
                    and current.get("engine") == "video"):
                self.store.update(item_id, engine="gallery", status=st.QUEUED,
                                  error="", speed="", eta="")
                self.item_changed.emit(item_id)
                return
            self._finish_failed(item_id, current, error)

    def _finish_failed(self, item_id, item, error):
        retries = int(item.get("retries") or 0)
        if retries < MAX_AUTO_RETRIES:
            self.store.update(item_id, status=st.FAILED, error=error,
                              retries=retries + 1, speed="", eta="")
            self._retry_at[item_id] = (time.monotonic()
                                       + RETRY_BACKOFF * (retries + 1))
        else:
            self.store.update(item_id, status=st.FAILED, error=error,
                              speed="", eta="")
        self.item_changed.emit(item_id)
