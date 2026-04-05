#!/usr/bin/env python3
"""Compare Ollama chat latency (and rough Ollama RSS) across models — same prompt, repeated runs."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from typing import Any

import requests

DEFAULT_PROMPT = """You are a music sample librarian. Given this pad request, reply with ONLY compact JSON keys:
type_code (3-letter), playability, vibe (array), genre (array), keywords (array).

Pad request: "dusty funk break loop, vinyl crackle, 95 bpm, warm"
"""


def _ollama_main_pid() -> int | None:
    try:
        out = subprocess.check_output(["pgrep", "-x", "ollama"], text=True).strip()
        if not out:
            return None
        return int(out.splitlines()[0])
    except (subprocess.CalledProcessError, ValueError):
        return None


class _MemSampler:
    def __init__(self, pid: int | None, interval: float = 0.15):
        self.pid = pid
        self.interval = interval
        self._stop = threading.Event()
        self.peak_rss_mb = 0.0
        self._thread: threading.Thread | None = None

    def _sample_loop(self):
        while not self._stop.is_set():
            if self.pid:
                try:
                    out = subprocess.check_output(
                        ["ps", "-o", "rss=", "-p", str(self.pid)], text=True, timeout=2
                    )
                    rss_kb = int(out.strip() or 0)
                    self.peak_rss_mb = max(self.peak_rss_mb, rss_kb / 1024.0)
                except (subprocess.CalledProcessError, ValueError):
                    pass
            time.sleep(self.interval)

    def start(self):
        if self.pid:
            self._thread = threading.Thread(target=self._sample_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def chat_once(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
    mem_pid: int | None,
) -> tuple[float, dict[str, Any], float]:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    sampler = _MemSampler(mem_pid)
    sampler.start()
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    finally:
        sampler.stop()
    elapsed = time.perf_counter() - t0
    usage = data.get("usage") or {}
    return elapsed, usage, sampler.peak_rss_mb


def run_benchmark(
    base_url: str,
    models: list[str],
    runs: int,
    warmup: int,
    prompt: str,
    max_tokens: int,
    timeout: int,
    out_path: str | None = None,
) -> dict[str, Any]:
    mem_pid = _ollama_main_pid()
    results: dict[str, Any] = {
        "ollama_pid": mem_pid,
        "models": {},
        "prompt_chars": len(prompt),
        "max_tokens": max_tokens,
        "runs_per_model": runs,
        "warmup_per_model": warmup,
    }

    def _snapshot_write():
        if out_path:
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(results, indent=2) + "\n")

    for model in models:
        latencies: list[float] = []
        peaks: list[float] = []
        tokens_out: list[int] = []

        for w in range(warmup):
            print(f"[{model}] warmup {w + 1}/{warmup} …", flush=True, file=sys.stderr)
            chat_once(base_url, model, prompt, max_tokens, timeout, mem_pid)

        for i in range(runs):
            print(f"[{model}] run {i + 1}/{runs} …", flush=True, file=sys.stderr)
            elapsed, usage, peak = chat_once(
                base_url, model, prompt, max_tokens, timeout, mem_pid
            )
            latencies.append(elapsed)
            peaks.append(peak)
            toks = usage.get("completion_tokens")
            if toks is not None:
                tokens_out.append(int(toks))

        def pct(xs: list[float], p: float) -> float:
            if not xs:
                return 0.0
            xs = sorted(xs)
            k = (len(xs) - 1) * p / 100.0
            f = int(k)
            c = min(f + 1, len(xs) - 1)
            return xs[f] + (xs[c] - xs[f]) * (k - f)

        results["models"][model] = {
            "runs": runs,
            "latency_s": {
                "mean": round(statistics.mean(latencies), 3),
                "median": round(statistics.median(latencies), 3),
                "p90": round(pct(latencies, 90), 3),
                "min": round(min(latencies), 3),
                "max": round(max(latencies), 3),
            },
            "tok_per_s_mean": (
                round(statistics.mean([t / latencies[i] for i, t in enumerate(tokens_out)]), 1)
                if len(tokens_out) == len(latencies)
                else None
            ),
            "completion_tokens_sample": tokens_out[:3] if tokens_out else None,
            "ollama_rss_peak_mb": {
                "mean": round(statistics.mean(peaks), 0) if peaks else None,
                "max": round(max(peaks), 0) if peaks else None,
            },
        }
        _snapshot_write()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Ollama models (latency + sampled RSS)")
    parser.add_argument("--url", default="http://127.0.0.1:11434", help="Ollama base URL")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen3:8b", "qwen3:32b"],
        help="Model tags as shown by `ollama list`",
    )
    parser.add_argument("--runs", type=int, default=5, help="Timed runs per model (after warmup)")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per model (discarded)")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--prompt-file", help="UTF-8 file with exact user prompt")
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="Write full JSON results to this file (in addition to stdout)",
    )
    args = parser.parse_args()

    prompt = DEFAULT_PROMPT
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            prompt = f.read()

    out = run_benchmark(
        args.url,
        args.models,
        args.runs,
        args.warmup,
        prompt,
        args.max_tokens,
        args.timeout,
        out_path=args.out,
    )
    text = json.dumps(out, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
