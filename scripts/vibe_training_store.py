"""Persistent storage for vibe supervision, eval sourcing, and retrieval."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from jambox_config import load_settings_for_script


SETTINGS = load_settings_for_script(__file__)
DB_PATH = SETTINGS["VIBE_SESSIONS_DB"]


def _json(value):
    return json.dumps(value or {}, sort_keys=True)


def _json_or_null(value):
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vibe_sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            dataset_status TEXT NOT NULL,
            session_status TEXT NOT NULL,
            model_mode TEXT NOT NULL,
            model_label TEXT,
            prompt TEXT NOT NULL,
            bank TEXT,
            bpm INTEGER,
            musical_key TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            fallback_code TEXT,
            fallback_reason TEXT,
            query TEXT,
            parsed_json TEXT,
            reviewed_parsed_json TEXT,
            draft_preset_json TEXT,
            reviewed_preset_json TEXT,
            applied_preset_json TEXT,
            bank_suggestions_json TEXT,
            sample_suggestions_json TEXT,
            fetch_enabled INTEGER,
            fetch_summary_json TEXT,
            fetch_result_text TEXT,
            fetch_error_text TEXT,
            preset_ref TEXT,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vibe_sessions_created_at
        ON vibe_sessions(created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vibe_sessions_dataset_status
        ON vibe_sessions(dataset_status)
        """
    )
    return conn


def _normalize_label(settings):
    mode = settings.get("VIBE_PARSER_MODE", "base")
    if mode == "fine_tuned":
        return settings.get("FINE_TUNED_LLM_MODEL") or settings.get("LLM_MODEL", "qwen3")
    return settings.get("LLM_MODEL", "qwen3")


def create_session(prompt_payload, result_payload, settings, db_path=None):
    session_id = str(uuid.uuid4())
    now = _utcnow()
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO vibe_sessions (
                id, created_at, updated_at, dataset_status, session_status, model_mode, model_label,
                prompt, bank, bpm, musical_key, fallback_used, fallback_code, fallback_reason, query,
                parsed_json, reviewed_parsed_json, draft_preset_json, reviewed_preset_json, applied_preset_json,
                bank_suggestions_json, sample_suggestions_json, fetch_enabled, fetch_summary_json,
                fetch_result_text, fetch_error_text, preset_ref, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                now,
                now,
                "raw",
                "generated",
                settings.get("VIBE_PARSER_MODE", "base"),
                _normalize_label(settings),
                prompt_payload.get("prompt", ""),
                prompt_payload.get("bank"),
                prompt_payload.get("bpm"),
                prompt_payload.get("key"),
                1 if result_payload.get("fallback_used") else 0,
                result_payload.get("fallback_code"),
                result_payload.get("fallback_reason"),
                result_payload.get("query"),
                _json_or_null(result_payload.get("parsed")),
                None,
                _json_or_null(result_payload.get("draft_preset")),
                None,
                None,
                _json_or_null(result_payload.get("bank_suggestions", [])),
                _json_or_null(result_payload.get("sample_suggestions", [])),
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )
    conn.close()
    return session_id


def update_review(session_id, reviewed_preset, reviewed_parsed, fetch_enabled, bank, db_path=None):
    now = _utcnow()
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """
            UPDATE vibe_sessions
            SET updated_at = ?, session_status = ?, bank = ?, reviewed_preset_json = ?,
                reviewed_parsed_json = ?, fetch_enabled = ?
            WHERE id = ?
            """,
            (
                now,
                "reviewed",
                bank,
                _json_or_null(reviewed_preset),
                _json_or_null(reviewed_parsed),
                1 if fetch_enabled else 0,
                session_id,
            ),
        )
    conn.close()


def complete_apply(session_id, applied_preset, preset_ref, fetch_summary, fetch_result_text, db_path=None):
    now = _utcnow()
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """
            UPDATE vibe_sessions
            SET updated_at = ?, dataset_status = ?, session_status = ?, applied_preset_json = ?,
                preset_ref = ?, fetch_summary_json = ?, fetch_result_text = ?, fetch_error_text = NULL
            WHERE id = ?
            """,
            (
                now,
                "reviewed",
                "applied",
                _json_or_null(applied_preset),
                preset_ref,
                _json_or_null(fetch_summary),
                fetch_result_text,
                session_id,
            ),
        )
    conn.close()


def fail_apply(session_id, error_text, db_path=None):
    now = _utcnow()
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """
            UPDATE vibe_sessions
            SET updated_at = ?, session_status = ?, fetch_error_text = ?
            WHERE id = ?
            """,
            (now, "error", error_text, session_id),
        )
    conn.close()


def list_sessions(limit=50, dataset_status=None, db_path=None):
    conn = _connect(db_path)
    query = "SELECT * FROM vibe_sessions"
    params = []
    if dataset_status:
        query += " WHERE dataset_status = ?"
        params.append(dataset_status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def promote_dataset_status(session_id, dataset_status, db_path=None):
    now = _utcnow()
    conn = _connect(db_path)
    with conn:
        conn.execute(
            "UPDATE vibe_sessions SET updated_at = ?, dataset_status = ? WHERE id = ?",
            (now, dataset_status, session_id),
        )
    conn.close()
