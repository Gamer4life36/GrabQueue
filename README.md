# GrabQueue

**A persistent, resumable download queue for Windows.** Paste a link — it
downloads, retries on failure, and survives restarts. Free, no ads, no
subscription, no account.

GrabQueue is a friendly front-end for the excellent open-source engines
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and
[gallery-dl](https://codeberg.org/mikf/gallery-dl). It adds the things those
command-line tools deliberately leave out: a real download queue that
remembers its state, automatic retries, status tracking, and one-click setup.

## Why it exists

The best downloaders are command-line only, and they intentionally don't
manage a persistent queue. GrabQueue fills that gap with a clean Windows GUI:

- **Persistent queue** — close the app mid-download and your queue is exactly
  where you left it when you reopen. Nothing is lost.
- **Automatic retries** — failed downloads retry on their own with backoff.
- **Parallel downloads** with live progress, speed, and ETA per item.
- **Playlists** expand into individual, trackable items.
- **Images & galleries too** — gallery-dl handles art sites, boorus, social
  media galleries; GrabQueue auto-falls-back to it when a link isn't a video.
- **Zero setup** — yt-dlp, gallery-dl and FFmpeg download themselves on first
  launch and keep themselves updated. No PATH fiddling, no separate installs.
- **Browser cookies** — one dropdown to download members-only / age-gated
  content you already have access to.

## Install

Download the latest `GrabQueue.exe` from the
[Releases](../../releases) page and run it. That's it — the download engines
are fetched automatically the first time you launch.

> First launch downloads ~120 MB of engines (yt-dlp + FFmpeg + gallery-dl).
> This is a one-time step.

## Supported sites

Over 1,700 video/audio extractors and hundreds of image-gallery sites —
YouTube, TikTok, X/Twitter, Reddit, Vimeo, SoundCloud, Instagram, DeviantArt,
Pixiv, and many more. See [SUPPORTED_SITES.txt](SUPPORTED_SITES.txt) for the
full list. Anything with a direct file link works too.

**DRM-protected services (Netflix, Disney+, Spotify, …) are not supported and
never will be.**

## Building from source

Requires Python 3.11+ and PySide6.

```
pip install PySide6
python main.py
```

To build the standalone exe:

```
pip install pyinstaller
python -m PyInstaller GrabQueue.spec --distpath . --workpath build -y
```

## Legal

GrabQueue is provided for entertainment and personal use. You are solely
responsible for how you use it and for respecting copyright and the terms of
service of the sites you download from. See [DISCLAIMER.txt](DISCLAIMER.txt).
GrabQueue contains no DRM-circumvention technology.

## Support

GrabQueue is free. If it saves you time, you can
[buy me a coffee](https://paypal.me/gamer4life33). 💛

## License

[MIT](LICENSE) for GrabQueue's own code. The download engines it uses are
separate open-source projects under their own licenses.
