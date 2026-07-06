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

### "Windows protected your PC"?

GrabQueue is a small independent app and isn't code-signed (a signing
certificate costs hundreds of dollars a year). Windows SmartScreen shows a
blue warning for any unsigned app it hasn't seen before — this is expected,
not a sign of a problem. To run it:

1. Click **More info**
2. Click **Run anyway**

The source is fully open in this repo if you'd like to review or build it
yourself before running.

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

GrabQueue is a free tool provided for **entertainment and personal use**. On
first launch you're asked to accept these terms once. In short:

1. **Sole responsibility** — you alone are responsible for how you use this
   software and for any content you download with it.
2. **Respect the law** — only download content you have the legal right to
   access and save. Do not use GrabQueue to infringe copyright, bypass
   paywalls, or circumvent DRM. It contains **no** circumvention technology.
3. **Terms of service** — downloading from a site may violate its terms; know
   the rules of the sites you use, and any consequences are yours.
4. **Personal use** — downloads are for your own personal, non-commercial use
   unless the rights holder permits otherwise. Don't redistribute them.
5. **No warranty** — provided "AS IS"; the author is not liable for any
   damages arising from its use.
6. **Not legal advice.**

Full text: [DISCLAIMER.txt](DISCLAIMER.txt).

## Support

GrabQueue is free. If it saves you time, you can
[buy me a coffee](https://paypal.me/gamer4life33). 💛

## License

[MIT](LICENSE) for GrabQueue's own code. The download engines it uses are
separate open-source projects under their own licenses.
