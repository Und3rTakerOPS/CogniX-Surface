# FIRMA ELIAD - NON MODIFICABILE
"""CogniX Surface — SQLite persistence layer.

Provides durable storage for triage items, filter presets, KPI timeline
snapshots and audit log entries. All functions are thread-safe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_local = threading.local()
_db_path: str = ""


# ── Connection management ────────────────────────────────────────────────────

def init_db(db_path: str) -> None:
    """Initialise the database, creating tables if needed."""
    global _db_path
    _db_path = db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread connection (SQLite is not thread-safe by default)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS triage_items (
    id          TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filter_presets (
    name        TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    details     TEXT,
    created_at  TEXT NOT NULL
);
"""


# ── Triage ───────────────────────────────────────────────────────────────────

def save_triage_item(item_id: str, data: dict[str, Any]) -> None:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO triage_items (id, data, updated_at) VALUES (?, ?, ?)",
        (item_id, json.dumps(data, default=str), now),
    )
    conn.commit()


def save_triage_items_bulk(items: dict[str, dict[str, Any]]) -> None:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR REPLACE INTO triage_items (id, data, updated_at) VALUES (?, ?, ?)",
        [(k, json.dumps(v, default=str), now) for k, v in items.items()],
    )
    conn.commit()


def load_triage_items() -> dict[str, dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute("SELECT id, data FROM triage_items").fetchall()
    return {row["id"]: json.loads(row["data"]) for row in rows}


def delete_triage_item(item_id: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM triage_items WHERE id = ?", (item_id,))
    conn.commit()


# ── Filter Presets ───────────────────────────────────────────────────────────

def save_filter_preset(name: str, data: dict[str, Any]) -> None:
    conn = _get_conn()
    now = data.get("created_at", datetime.now(timezone.utc).isoformat())
    conn.execute(
        "INSERT OR REPLACE INTO filter_presets (name, data, created_at) VALUES (?, ?, ?)",
        (name, json.dumps(data, default=str), now),
    )
    conn.commit()


def load_filter_presets() -> dict[str, dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute("SELECT name, data FROM filter_presets").fetchall()
    return {row["name"]: json.loads(row["data"]) for row in rows}


def delete_filter_preset(name: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM filter_presets WHERE name = ?", (name,))
    conn.commit()
    return cur.rowcount > 0


# ── KPI Timeline ────────────────────────────────────────────────────────────

def save_kpi_snapshot(snapshot: dict[str, Any]) -> None:
    conn = _get_conn()
    now = snapshot.get("timestamp", datetime.now(timezone.utc).isoformat())
    conn.execute(
        "INSERT INTO kpi_timeline (data, created_at) VALUES (?, ?)",
        (json.dumps(snapshot, default=str), now),
    )
    conn.commit()


def load_kpi_timeline(max_snapshots: int = 200) -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT data FROM kpi_timeline ORDER BY id DESC LIMIT ?",
        (max_snapshots,),
    ).fetchall()
    return [json.loads(row["data"]) for row in reversed(rows)]


def trim_kpi_timeline(max_snapshots: int = 200) -> None:
    conn = _get_conn()
    conn.execute(
        "DELETE FROM kpi_timeline WHERE id NOT IN "
        "(SELECT id FROM kpi_timeline ORDER BY id DESC LIMIT ?)",
        (max_snapshots,),
    )
    conn.commit()


# ── Audit Log ────────────────────────────────────────────────────────────────

def save_audit_entry(action: str, details: str = "") -> None:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO audit_log (action, details, created_at) VALUES (?, ?, ?)",
        (action, details, now),
    )
    conn.commit()


def load_audit_log(limit: int = 500) -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT action, details, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]
