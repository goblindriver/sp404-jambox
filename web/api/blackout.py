"""Blackout-mode dashboard: offline training health without LLM daemons."""

from __future__ import annotations

import json
import os
import sqlite3

import yaml
from flask import Blueprint, current_app, jsonify

blackout_bp = Blueprint("blackout", __name__)


def _check_path(repo_dir: str, entry: dict) -> dict:
    path = os.path.join(repo_dir, entry["path"])
    if entry["type"] == "dir":
        ok = os.path.isdir(path)
        file_count = len(os.listdir(path)) if ok else 0
        ok = ok and file_count >= entry.get("minimum_files", 0)
        return {"path": entry["path"], "ok": ok, "file_count": file_count}
    return {"path": entry["path"], "ok": os.path.isfile(path)}


def _vibe_session_stats(db_path: str) -> dict:
    if not os.path.isfile(db_path):
        return {"db_exists": False, "total": 0, "by_dataset_status": {}}
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vibe_sessions'"
        ).fetchone()
        if not row:
            conn.close()
            return {"db_exists": True, "total": 0, "by_dataset_status": {}}
        counts = conn.execute(
            "SELECT dataset_status, COUNT(*) FROM vibe_sessions GROUP BY dataset_status"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM vibe_sessions").fetchone()[0]
        conn.close()
        return {
            "db_exists": True,
            "total": total,
            "by_dataset_status": {status: n for status, n in counts},
        }
    except sqlite3.Error:
        return {"db_exists": True, "total": None, "by_dataset_status": {}, "error": "sqlite_error"}


def _eval_suite(repo_dir: str, eval_dir: str) -> dict:
    names = [
        "prompt_to_parse.jsonl",
        "prompt_to_draft.jsonl",
        "prompt_to_ranking.jsonl",
        "ranking_fixture.json",
    ]
    files = {}
    for name in names:
        p = os.path.join(eval_dir, name)
        files[name] = os.path.isfile(p)
    return {
        "dir": eval_dir,
        "files": files,
        "all_present": all(files.values()),
    }


def _training_export(repo_dir: str) -> dict:
    out_dir = os.path.join(repo_dir, "data", "training", "vibe")
    summary_path = os.path.join(out_dir, "summary.json")
    summary = None
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as handle:
                summary = json.load(handle)
        except (OSError, json.JSONDecodeError):
            summary = None
    parse_path = os.path.join(out_dir, "parse_train.jsonl")
    draft_path = os.path.join(out_dir, "draft_train.jsonl")
    return {
        "dir": out_dir,
        "dir_exists": os.path.isdir(out_dir),
        "summary": summary,
        "parse_train_bytes": os.path.getsize(parse_path) if os.path.isfile(parse_path) else 0,
        "draft_train_bytes": os.path.getsize(draft_path) if os.path.isfile(draft_path) else 0,
    }


def _pattern_readiness(repo_dir: str, checkpoint_dir: str) -> dict:
    req_path = os.path.join(repo_dir, "training", "pattern", "requirements.yaml")
    checks = []
    if os.path.isfile(req_path):
        with open(req_path, encoding="utf-8") as handle:
            requirements = yaml.safe_load(handle) or {}
        checks = [_check_path(repo_dir, e) for e in requirements.get("required_paths", [])]
    ck_ok = bool(checkpoint_dir) and os.path.isdir(checkpoint_dir)
    ready = ck_ok and checks and all(c["ok"] for c in checks)
    return {
        "checks": checks,
        "checkpoint_dir": checkpoint_dir or "",
        "checkpoint_ready": ck_ok,
        "ready": ready,
    }


def _lora_artifacts(repo_dir: str) -> dict:
    script = os.path.join(repo_dir, "training", "vibe", "train_lora.py")
    cfg_dir = os.path.join(repo_dir, "training", "vibe", "configs")
    configs = []
    if os.path.isdir(cfg_dir):
        configs = sorted(f for f in os.listdir(cfg_dir) if f.endswith((".yaml", ".yml")))
    return {
        "train_script": os.path.isfile(script),
        "config_dir": cfg_dir,
        "config_files": configs,
    }


@blackout_bp.route("/blackout/status")
def blackout_status():
    """JSON snapshot for offline eval, supervision data, and training gates."""
    cfg = current_app.config
    repo_dir = cfg["REPO_DIR"]
    eval_dir = cfg.get("VIBE_EVAL_DIR") or os.path.join(repo_dir, "data", "evals")
    db_path = cfg.get("VIBE_SESSIONS_DB") or os.path.join(repo_dir, "data", "vibe_sessions.sqlite")
    checkpoint_dir = cfg.get("MUSICVAE_CHECKPOINT_DIR") or ""

    llm = bool(cfg.get("LLM_ENDPOINT", "").strip())
    ft_llm = bool(cfg.get("FINE_TUNED_LLM_ENDPOINT", "").strip())
    parser_mode = cfg.get("VIBE_PARSER_MODE", "base")
    eval_suite = _eval_suite(repo_dir, eval_dir)
    session_stats = _vibe_session_stats(db_path)
    export_info = _training_export(repo_dir)
    pattern = _pattern_readiness(repo_dir, checkpoint_dir)
    lora = _lora_artifacts(repo_dir)

    reviewed = session_stats.get("by_dataset_status", {}).get("reviewed", 0) or 0
    offline_core = eval_suite["all_present"]
    needs_llm_for_mode = parser_mode in ("rag", "fine_tuned")
    llm_ready = llm if parser_mode in ("base", "rag") else ft_llm

    return jsonify(
        {
            "ok": True,
            "llm_endpoint_configured": llm,
            "fine_tuned_endpoint_configured": ft_llm,
            "vibe_parser_mode": parser_mode,
            "parser_needs_llm": needs_llm_for_mode,
            "parser_llm_ready": bool(llm_ready),
            "offline_eval_ready": offline_core,
            "keyword_fallback_ready": True,
            "vibe_sessions": {
                "db_path": db_path,
                **session_stats,
                "reviewed_count": reviewed,
            },
            "eval_suite": eval_suite,
            "training_export": export_info,
            "pattern_training": pattern,
            "lora": lora,
        }
    )
