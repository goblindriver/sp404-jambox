#!/usr/bin/env python3
"""Validate local JamBox runtime prerequisites and optional integrations."""

from __future__ import annotations

import importlib.util
import os
import sys

from jambox_config import (
    ConfigError,
    build_subprocess_env,
    load_settings_for_script,
    load_tag_db,
    resolve_command,
)


REQUIRED_PYTHON_MODULES = {
    "Flask": "flask",
    "mutagen": "mutagen",
    "numpy": "numpy",
    "PyYAML": "yaml",
    "requests": "requests",
    "watchdog": "watchdog",
}


def _module_installed(module_name):
    return importlib.util.find_spec(module_name) is not None


def _status(ok, label, detail=""):
    prefix = "OK" if ok else "MISSING"
    suffix = f" - {detail}" if detail else ""
    return f"[{prefix}] {label}{suffix}"


def _integration_status(enabled, label, detail=""):
    prefix = "READY" if enabled else "OPTIONAL"
    suffix = f" - {detail}" if detail else ""
    return f"[{prefix}] {label}{suffix}"


def run_checks():
    messages = []
    failures = 0
    warnings = 0

    try:
        settings = load_settings_for_script(__file__)
    except ConfigError as exc:
        print(_status(False, "Configuration", str(exc)))
        return 1

    env = build_subprocess_env(settings)
    repo_dir = settings["REPO_DIR"]

    messages.append("Python modules:")
    for display_name, module_name in REQUIRED_PYTHON_MODULES.items():
        ok = _module_installed(module_name)
        messages.append(f"  {_status(ok, display_name)}")
        if not ok:
            failures += 1

    messages.append("")
    messages.append("Core tools:")
    for label, key in (
        ("ffmpeg", "FFMPEG_BIN"),
        ("ffprobe", "FFPROBE_BIN"),
        ("unar", "UNAR_BIN"),
    ):
        resolved = resolve_command(settings[key], env)
        ok = resolved is not None
        messages.append(f"  {_status(ok, label, resolved or settings[key])}")
        if not ok:
            failures += 1

    messages.append("")
    messages.append("Optional integrations:")
    fpcalc = resolve_command(settings["FINGERPRINT_TOOL"], env)
    messages.append(
        f"  {_integration_status(fpcalc is not None, 'fpcalc / Chromaprint', fpcalc or settings['FINGERPRINT_TOOL'])}"
    )
    if fpcalc is None:
        warnings += 1

    magenta = resolve_command(settings["MAGENTA_COMMAND"], env)
    checkpoint_dir = settings.get("MUSICVAE_CHECKPOINT_DIR", "")
    magenta_ready = magenta is not None and bool(checkpoint_dir) and os.path.isdir(checkpoint_dir)
    magenta_detail = []
    magenta_detail.append(magenta or settings["MAGENTA_COMMAND"])
    if checkpoint_dir:
        magenta_detail.append(f"checkpoints={checkpoint_dir}")
    else:
        magenta_detail.append("checkpoints not configured")
    messages.append(
        f"  {_integration_status(magenta_ready, 'Magenta pattern generation', '; '.join(magenta_detail))}"
    )
    if not magenta_ready:
        warnings += 1

    llm_endpoint = settings.get("LLM_ENDPOINT", "").strip()
    llm_ready = bool(llm_endpoint)
    llm_detail = llm_endpoint or "SP404_LLM_ENDPOINT not set"
    messages.append(f"  {_integration_status(llm_ready, 'Natural-language vibe parsing', llm_detail)}")
    if not llm_ready:
        warnings += 1

    parser_mode = settings.get("VIBE_PARSER_MODE", "base")
    mode_detail = f"mode={parser_mode}; model={settings.get('LLM_MODEL', 'qwen3')}"
    if parser_mode == "fine_tuned":
        tuned_endpoint = settings.get("FINE_TUNED_LLM_ENDPOINT", "").strip()
        tuned_model = settings.get("FINE_TUNED_LLM_MODEL", "").strip() or "(unset)"
        tuned_ready = bool(tuned_endpoint)
        tuned_detail = (tuned_endpoint or "SP404_FINE_TUNED_LLM_ENDPOINT not set") + f"; model={tuned_model}"
        messages.append(
            f"  {_integration_status(tuned_ready, 'Fine-tuned vibe parser', tuned_detail)}"
        )
        if not tuned_ready:
            warnings += 1
    else:
        messages.append(f"  {_integration_status(True, 'Vibe parser mode', mode_detail)}")

    split_sec = settings.get("SMART_RETAG_DURATION_SPLIT_SEC", 60)
    long_m = (settings.get("SMART_RETAG_LLM_MODEL") or "").strip() or "qwen3.5:9b"
    base_m = settings.get("LLM_MODEL", "qwen3")
    skip_v = settings.get("SMART_RETAG_SKIP_ABOVE_SECONDS")
    skip_part = f"; skip LLM if duration >= {skip_v}s" if skip_v else ""
    retag_detail = f"<={split_sec}s: {base_m}; >{split_sec}s: {long_m}{skip_part}"
    messages.append(f"  {_integration_status(True, 'Smart retag LLM routing', retag_detail)}")

    messages.append("")
    messages.append("Configured paths:")
    for label, value, should_exist in (
        ("Repository", repo_dir, True),
        ("bank_config.yaml", settings["CONFIG_PATH"], True),
        ("Vibe sessions DB", settings.get("VIBE_SESSIONS_DB", os.path.join(repo_dir, "data", "vibe_sessions.sqlite")), False),
        ("Vibe eval dir", settings.get("VIBE_EVAL_DIR", os.path.join(repo_dir, "data", "evals")), False),
        ("Sample library", settings["SAMPLE_LIBRARY"], False),
        ("Downloads path", settings["DOWNLOADS_PATH"], False),
        ("SD card mount", settings["SD_CARD"], False),
        ("sd-card-template SMPL", settings["SMPL_DIR"], True),
    ):
        exists = os.path.exists(value)
        detail = value if exists or not should_exist else f"{value} (missing)"
        messages.append(f"  {_status(exists or not should_exist, label, detail)}")
        if should_exist and not exists:
            failures += 1

    messages.append("")
    messages.append("Tag database health:")
    tags_file = settings.get("TAGS_FILE", os.path.join(settings["SAMPLE_LIBRARY"], "_tags.json"))
    if os.path.isfile(tags_file):
        try:
            tag_db = load_tag_db(tags_file)
            total = len(tag_db)
            smart_v1 = sum(1 for e in tag_db.values() if e.get("tag_source") == "smart_retag_v1")
            pending = sum(1 for e in tag_db.values() if e.get("smart_retag_pending"))
            baseline = total - smart_v1 - pending
            quality_scores = [e["quality_score"] for e in tag_db.values()
                              if isinstance(e.get("quality_score"), (int, float))]
            avg_q = (sum(quality_scores) / len(quality_scores)) if quality_scores else 0

            long_hold_dir = os.path.join(settings["SAMPLE_LIBRARY"], "_LONG-HOLD")
            quarantine_dir = os.path.join(settings["SAMPLE_LIBRARY"], "_QUARANTINE")
            long_hold_count = sum(1 for e in tag_db.values()
                                  if "_LONG-HOLD" in e.get("path", ""))
            quarantine_count = 0
            if os.path.isdir(quarantine_dir):
                for _root, _dirs, _files in os.walk(quarantine_dir):
                    quarantine_count += len(_files)

            messages.append("  Total entries: %d" % total)
            messages.append("  smart_retag_v1 (full LLM): %d (%.0f%%)" %
                            (smart_v1, smart_v1 / max(total, 1) * 100))
            messages.append("  smart_retag_pending (features, no LLM): %d (%.0f%%)" %
                            (pending, pending / max(total, 1) * 100))
            messages.append("  Baseline-only: %d (%.0f%%)" %
                            (baseline, baseline / max(total, 1) * 100))
            if quality_scores:
                messages.append("  Mean quality_score: %.1f (n=%d)" % (avg_q, len(quality_scores)))
            messages.append("  _LONG-HOLD entries: %d" % long_hold_count)
            messages.append("  _QUARANTINE files: %d" % quarantine_count)
        except Exception as exc:
            messages.append("  ERROR reading tag DB: %s" % exc)
            warnings += 1
    else:
        messages.append("  [MISSING] %s" % tags_file)
        messages.append("  Run: python scripts/tag_library.py")
        warnings += 1

    messages.append("")
    messages.append("Hints:")
    messages.append("  - Install Python deps with: .venv/bin/pip install -r requirements.txt")
    messages.append("  - On macOS/Homebrew: brew install ffmpeg unar chromaprint")
    messages.append("  - Set SP404_LLM_ENDPOINT to enable natural-language prompts.")
    messages.append("  - Set SP404_VIBE_PARSER_MODE=rag or fine_tuned to evaluate grounded/tuned parsing.")
    messages.append("  - Set SP404_MAGENTA_COMMAND and SP404_MUSICVAE_CHECKPOINT_DIR to enable Magenta patterns.")
    messages.append("")
    messages.append(f"Summary: {failures} blocking issue(s), {warnings} optional integration warning(s)")

    print("\n".join(messages))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_checks())
