"""Persistent download queue backed by SQLite.

Every mutation is committed immediately so the queue survives crashes,
restarts, and power loss — the core promise of GrabQueue.
"""
import os
import sqlite3
import threading
import time

# item statuses
QUEUED = "queued"
FETCHING = "starting"
DOWNLOADING = "downloading"
CONVERTING = "converting"
DONE = "done"
FAILED = "failed"
PAUSED = "paused"
CANCELED = "canceled"

ACTIVE = (FETCHING, DOWNLOADING, CONVERTING)


class QueueStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT NOT NULL,
                title       TEXT DEFAULT '',
                status      TEXT DEFAULT 'queued',
                progress    REAL DEFAULT 0,
                size        TEXT DEFAULT '',
                speed       TEXT DEFAULT '',
                eta         TEXT DEFAULT '',
                preset      TEXT DEFAULT '',
                output_dir  TEXT DEFAULT '',
                file_path   TEXT DEFAULT '',
                error       TEXT DEFAULT '',
                retries     INTEGER DEFAULT 0,
                added_at    REAL,
                finished_at REAL,
                engine      TEXT DEFAULT 'video'
            )""")
        self._db.commit()
        try:  # migrate pre-engine databases
            self._db.execute(
                "ALTER TABLE items ADD COLUMN engine TEXT DEFAULT 'video'")
            self._db.commit()
        except sqlite3.OperationalError:
            pass

    def add(self, url, preset, output_dir, engine="video", title=""):
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO items (url, preset, output_dir, status, added_at, "
                "engine, title) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (url, preset, output_dir, QUEUED, time.time(), engine, title))
            self._db.commit()
            return cur.lastrowid

    def update(self, item_id, **fields):
        if not fields:
            return
        with self._lock:
            cols = ", ".join(f"{k} = ?" for k in fields)
            self._db.execute(f"UPDATE items SET {cols} WHERE id = ?",
                             (*fields.values(), item_id))
            self._db.commit()

    def get(self, item_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM items WHERE id = ?",
                                   (item_id,)).fetchone()
            return dict(row) if row else None

    def all_items(self):
        with self._lock:
            return [dict(r) for r in
                    self._db.execute("SELECT * FROM items ORDER BY id").fetchall()]

    def next_queued(self):
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM items WHERE status = ? ORDER BY id LIMIT 1",
                (QUEUED,)).fetchone()
            return dict(row) if row else None

    def count(self, *statuses):
        with self._lock:
            marks = ",".join("?" * len(statuses))
            return self._db.execute(
                f"SELECT COUNT(*) FROM items WHERE status IN ({marks})",
                statuses).fetchone()[0]

    def reset_interrupted(self):
        """Anything that was mid-download when the app died goes back in line."""
        with self._lock:
            self._db.execute(
                "UPDATE items SET status = ?, speed = '', eta = '' "
                "WHERE status IN (?, ?, ?)",
                (QUEUED, *ACTIVE))
            self._db.commit()

    def requeue_failed(self):
        with self._lock:
            self._db.execute(
                "UPDATE items SET status = ?, error = '', retries = 0 "
                "WHERE status = ?", (QUEUED, FAILED))
            self._db.commit()

    def remove(self, item_ids):
        with self._lock:
            marks = ",".join("?" * len(item_ids))
            self._db.execute(f"DELETE FROM items WHERE id IN ({marks})", item_ids)
            self._db.commit()

    def clear_finished(self):
        with self._lock:
            self._db.execute("DELETE FROM items WHERE status IN (?, ?)",
                             (DONE, CANCELED))
            self._db.commit()

    def close(self):
        with self._lock:
            self._db.close()
