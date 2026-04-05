"""Blackout-mode dashboard: offline training health without LLM daemons."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import sys

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


def _pgrep_script_running(fragment: str) -> bool:
    """True if a local process command line contains the fragment (e.g. scripts/smart_retag.py)."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", fragment],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return proc.returncode == 0 and bool((proc.stdout or "").strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


def _retag_checkpoint_summary(repo_root: str) -> dict | None:
    path = os.path.join(repo_root, "data", "retag_checkpoint.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"error": "read_failed"}
    return {
        "path": path,
        "last_updated": data.get("last_updated"),
        "processed": data.get("processed"),
        "total_files": data.get("total_files"),
        "tagged": data.get("tagged"),
        "quarantined": data.get("quarantined"),
        "errors": data.get("errors"),
        "batch_size": data.get("batch_size"),
        "llm_stats": data.get("llm_stats"),
    }


def _tail_text_file(path: str, max_lines: int = 4, chunk: int = 6144) -> list[str]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - chunk), os.SEEK_SET)
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    out = lines[-max_lines:] if len(lines) > max_lines else lines
    return [ln if len(ln) <= 160 else ln[:157] + "…" for ln in out]


def _ollama_family_rss_mb() -> float | None:
    """Sum RSS for Ollama server + runners (unified-memory proxy for LLM weights)."""
    try:
        import psutil
    except ImportError:
        return None
    total = 0
    found = False
    for proc in psutil.process_iter():
        try:
            cmd = proc.cmdline()
            if not cmd:
                continue
            exe = os.path.basename(cmd[0]).lower()
            if exe != "ollama":
                continue
            total += proc.memory_info().rss
            found = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue
    if not found:
        return None
    return round(total / (1024 * 1024), 0)


def _host_metrics() -> dict:
    """CPU, RAM, swap, load; GPU % not available without privileged macOS samplers."""
    out: dict = {
        "cpu_percent": None,
        "memory_percent": None,
        "memory_used_gb": None,
        "memory_total_gb": None,
        "memory_available_gb": None,
        "swap_used_gb": None,
        "swap_percent": None,
        "load_1m": None,
        "server_rss_mb": None,
        "ollama_rss_mb": None,
        "platform": sys.platform,
        "machine": platform.machine(),
        "gpu": {
            "utilization_percent": None,
            "label": "Apple Silicon (Metal)" if sys.platform == "darwin" and platform.machine() == "arm64" else "GPU",
            "note": (
                "macOS does not expose a stable GPU % API without root (e.g. powermetrics). "
                "Use Activity Monitor → Window → GPU History. On Apple Silicon, LLM weights live in unified memory — "
                "watch RAM + Ollama RSS."
            ),
        },
    }
    try:
        import psutil
    except ImportError:
        out["error"] = "psutil_not_installed"
        return out

    out["cpu_percent"] = round(psutil.cpu_percent(interval=0.12), 1)
    vm = psutil.virtual_memory()
    out["memory_percent"] = round(vm.percent, 1)
    out["memory_used_gb"] = round(vm.used / (1024**3), 2)
    out["memory_total_gb"] = round(vm.total / (1024**3), 2)
    out["memory_available_gb"] = round(vm.available / (1024**3), 2)
    sw = psutil.swap_memory()
    out["swap_used_gb"] = round(sw.used / (1024**3), 2)
    out["swap_percent"] = round(sw.percent, 1) if sw.total else 0.0
    try:
        out["load_1m"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    try:
        out["server_rss_mb"] = round(
            psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 0
        )
    except (psutil.Error, OSError):
        pass
    out["ollama_rss_mb"] = _ollama_family_rss_mb()
    return out


def _resolve_crunch_root(cfg: dict) -> tuple[str, str, bool]:
    """Return (crunch_repo_root, source, invalid_env).

    source is \"env\" when SP404_CRUNCH_REPO is set and valid, else \"app_repo\".
    invalid_env True when CRUNCH_REPO was set but is not a directory.
    """
    app_repo = cfg["REPO_DIR"]
    alt = (cfg.get("CRUNCH_REPO") or "").strip()
    if not alt:
        return app_repo, "app_repo", False
    if os.path.isdir(alt):
        return alt, "env", False
    return app_repo, "app_repo", True


def _live_crunch(crunch_root: str, source: str, invalid_crunch_repo: bool) -> dict:
    return {
        "watch_root": crunch_root,
        "watch_source": source,
        "crunch_repo_invalid": invalid_crunch_repo,
        "retag_checkpoint": _retag_checkpoint_summary(crunch_root),
        "processes": {
            "smart_retag": _pgrep_script_running("scripts/smart_retag.py"),
            "tag_library": _pgrep_script_running("scripts/tag_library.py"),
        },
        "log_snippets": {
            "tag_library": _tail_text_file(os.path.join(crunch_root, "data", "crunch_tag_library.log")),
            "retag": _tail_text_file(os.path.join(crunch_root, "data", "crunch_retag.log")),
        },
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

    crunch_root, crunch_source, crunch_invalid = _resolve_crunch_root(cfg)

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
            "live_crunch": _live_crunch(crunch_root, crunch_source, crunch_invalid),
            "host_metrics": _host_metrics(),
        }
    )
