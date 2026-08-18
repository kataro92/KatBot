"""SQLite history for telemetry, chat, and logs."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger("meobot.store")

WINDOWS_MS = {
    "1m": 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "3h": 3 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

MAX_CHART_POINTS = 720
_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  temp REAL,
  humidity REAL,
  state TEXT,
  device_online INTEGER,
  session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts);

CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  audio_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_ts ON chat(ts);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=4000")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn
        log.info("SQLite ready %s", self.path)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("store not open")
        return self._conn

    def insert_telemetry(
        self,
        ts: int,
        temp: float | None,
        humidity: float | None,
        state: str | None,
        device_online: bool | None,
        session_id: str | None,
    ) -> None:
        with self._lock:
            self._db().execute(
                "INSERT INTO telemetry(ts, temp, humidity, state, device_online, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    temp,
                    humidity,
                    state,
                    None if device_online is None else int(bool(device_online)),
                    session_id,
                ),
            )
            self._db().commit()

    def insert_chat(self, ts: int, role: str, text: str, audio_id: str | None) -> None:
        with self._lock:
            self._db().execute(
                "INSERT INTO chat(ts, role, text, audio_id) VALUES (?, ?, ?, ?)",
                (ts, role, text, audio_id),
            )
            self._db().commit()

    def insert_log(self, ts: int, level: str, message: str) -> None:
        with self._lock:
            self._db().execute(
                "INSERT INTO logs(ts, level, message) VALUES (?, ?, ?)",
                (ts, level, message),
            )
            self._db().commit()

    def telemetry(self, from_ms: int, to_ms: int) -> list[dict[str, Any]]:
        span = max(1, to_ms - from_ms)
        bucket = max(1000, span // MAX_CHART_POINTS)
        with self._lock:
            rows = self._db().execute(
                "SELECT (ts / ?) * ? AS t, AVG(temp) AS temp, AVG(humidity) AS humidity "
                "FROM telemetry "
                "WHERE ts >= ? AND ts <= ? AND (temp IS NOT NULL OR humidity IS NOT NULL) "
                "GROUP BY t ORDER BY t ASC",
                (bucket, bucket, from_ms, to_ms),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "t": int(row["t"]),
                    "temp": None if row["temp"] is None else float(row["temp"]),
                    "humidity": None if row["humidity"] is None else float(row["humidity"]),
                }
            )
        return out

    def chat(self, *, limit: int = 300) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        with self._lock:
            rows = self._db().execute(
                "SELECT ts, role, text, audio_id FROM chat ORDER BY ts DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = [
            {
                "ts": int(row["ts"]),
                "role": row["role"],
                "text": row["text"],
                "audio_id": row["audio_id"],
            }
            for row in rows
        ]
        items.reverse()
        return items

    def logs(self, *, limit: int = 300) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        with self._lock:
            rows = self._db().execute(
                "SELECT ts, level, message FROM logs ORDER BY ts DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = [
            {
                "ts": int(row["ts"]),
                "level": row["level"],
                "message": row["message"],
            }
            for row in rows
        ]
        items.reverse()
        return items


_store: Store | None = None


def init_store(path: str | Path | None = None) -> Store:
    global _store
    if _store is not None:
        _store.close()
    _store = Store(Path(path or settings.db_path))
    _store.open()
    return _store


def close_store() -> None:
    global _store
    if _store is not None:
        _store.close()
        _store = None


def db() -> Store:
    if _store is None:
        return init_store()
    return _store


def window_bounds(window: str | None, from_ms: int | None, to_ms: int | None) -> tuple[int, int]:
    now = int(time.time() * 1000)
    if from_ms is not None and to_ms is not None:
        start, end = int(from_ms), int(to_ms)
        if end <= start:
            raise ValueError("to_ms must be after from_ms")
        if end - start > 31 * WINDOWS_MS["1d"]:
            raise ValueError("range too large")
        return start, end
    span = WINDOWS_MS.get((window or "15m").strip().lower(), WINDOWS_MS["15m"])
    return now - span, now
