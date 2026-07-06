r"""Engine management: bundled yt-dlp + FFmpeg, downloaded and updated in-app.

Everything lives in <app>\engines so the user never installs a dependency.
"""
import os
import subprocess
import sys
import zipfile
from urllib.request import Request, urlopen

APP_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))
ENGINES_DIR = os.path.join(APP_DIR, "engines")

YTDLP_EXE = os.path.join(ENGINES_DIR, "yt-dlp.exe")
FFMPEG_EXE = os.path.join(ENGINES_DIR, "ffmpeg.exe")
GALLERYDL_EXE = os.path.join(ENGINES_DIR, "gallery-dl.exe")

YTDLP_URL = ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
             "yt-dlp.exe")
# gallery-dl publishes its binaries on Codeberg (migrated off GitHub 2026);
# there is no /latest/download shortcut, so resolve the asset via the API.
GALLERYDL_API = "https://codeberg.org/api/v1/repos/mikf/gallery-dl/releases/latest"
# BtbN's builds are the de-facto standard Windows FFmpeg binaries.
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
              "ffmpeg-master-latest-win64-gpl.zip")

NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def engines_ready():
    return (os.path.exists(YTDLP_EXE) and os.path.exists(FFMPEG_EXE)
            and os.path.exists(GALLERYDL_EXE))


def _download(url, dest, progress=None, label=""):
    req = Request(url, headers={"User-Agent": "GrabQueue/1.0"})
    tmp = dest + ".part"
    with urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(label, got / total)
    os.replace(tmp, dest)


def install_ytdlp(progress=None):
    os.makedirs(ENGINES_DIR, exist_ok=True)
    _download(YTDLP_URL, YTDLP_EXE, progress, "yt-dlp")


def install_ffmpeg(progress=None):
    os.makedirs(ENGINES_DIR, exist_ok=True)
    zpath = os.path.join(ENGINES_DIR, "ffmpeg.zip")
    _download(FFMPEG_URL, zpath, progress, "FFmpeg")
    if progress:
        progress("FFmpeg (extracting)", 1.0)
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                with z.open(name) as src, \
                        open(os.path.join(ENGINES_DIR, base), "wb") as dst:
                    dst.write(src.read())
    os.remove(zpath)


def install_gallerydl(progress=None):
    import json
    os.makedirs(ENGINES_DIR, exist_ok=True)
    req = Request(GALLERYDL_API, headers={"User-Agent": "GrabQueue/1.0"})
    with urlopen(req, timeout=30) as resp:
        release = json.load(resp)
    url = next(a["browser_download_url"] for a in release["assets"]
               if a["name"] == "gallery-dl.exe")
    _download(url, GALLERYDL_EXE, progress, "gallery-dl")


def gallerydl_version():
    if not os.path.exists(GALLERYDL_EXE):
        return None
    try:
        out = subprocess.run([GALLERYDL_EXE, "--version"], capture_output=True,
                             text=True, timeout=30, creationflags=NO_WINDOW)
        return out.stdout.strip() or None
    except Exception:
        return None


def ensure_engines(progress=None):
    """Install whichever engines are missing. Safe to call repeatedly."""
    if not os.path.exists(YTDLP_EXE):
        install_ytdlp(progress)
    if not os.path.exists(GALLERYDL_EXE):
        install_gallerydl(progress)
    if not os.path.exists(FFMPEG_EXE):
        install_ffmpeg(progress)


def ytdlp_version():
    if not os.path.exists(YTDLP_EXE):
        return None
    try:
        out = subprocess.run([YTDLP_EXE, "--version"], capture_output=True,
                             text=True, timeout=30, creationflags=NO_WINDOW)
        return out.stdout.strip() or None
    except Exception:
        return None


def update_ytdlp():
    """yt-dlp self-updates in place. Returns its output text."""
    try:
        out = subprocess.run([YTDLP_EXE, "-U"], capture_output=True, text=True,
                             timeout=180, creationflags=NO_WINDOW)
        return (out.stdout + out.stderr).strip()
    except Exception as e:
        return f"update failed: {e}"
