"""Durable local chat catalog and transcript cache (no external dependencies)."""
import json
import sqlite3


class Catalog:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=15)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            source TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (source, id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL,
            size INTEGER NOT NULL, data TEXT NOT NULL)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS hooks (
            id TEXT PRIMARY KEY, timestamp REAL NOT NULL, data TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY, activity REAL NOT NULL, first_seen REAL NOT NULL,
            notified INTEGER NOT NULL DEFAULT 0)""")

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.db.commit()
            else:
                self.db.rollback()
        finally:
            self.db.close()

    def cached_file(self, path, stat):
        row = self.db.execute(
            "SELECT data FROM files WHERE path=? AND mtime_ns=? AND size=?",
            (path, stat.st_mtime_ns, stat.st_size),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_file(self, path, stat, data):
        self.db.execute(
            "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)",
            (path, stat.st_mtime_ns, stat.st_size, json.dumps(data)),
        )

    def remember(self, record):
        self.db.execute(
            """INSERT INTO sessions VALUES (?, ?, ?)
            ON CONFLICT(source, id) DO UPDATE SET data=excluded.data
            WHERE sessions.data != excluded.data""",
            (record["item"][0], record["item"][1], json.dumps(record)),
        )

    def records(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT data FROM sessions")]

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    def hook(self, sid, timestamp, data):
        self.db.execute("""INSERT INTO hooks VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET timestamp=excluded.timestamp, data=excluded.data
            WHERE excluded.timestamp >= hooks.timestamp""", (sid, timestamp, json.dumps(data)))

    def hooks(self):
        return {row[0]: {**json.loads(row[2]), "timestamp": row[1]}
                for row in self.db.execute("SELECT id, timestamp, data FROM hooks")}
