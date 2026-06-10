#!/usr/bin/env python3
"""ProgettoTR web dashboard server.  stdlib only — no extra deps.

Usage:
    python web/server.py
    # or via avvia_dashboard.bat
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

PORT = 8050
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent


# ── subprocess wrapper ─────────────────────────────────────────────────────────

class ManagedProcess:
    """Thread-safe subprocess with captured output and polling-friendly log buffer."""

    def __init__(self, name: str, maxlines: int = 2000) -> None:
        self.name = name
        self._maxlines = maxlines
        self._proc: Optional[subprocess.Popen] = None
        self._lines: List[str] = []
        self._lock = threading.Lock()
        self.start_time: Optional[float] = None
        self.exit_code: Optional[int] = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, cmd: List[str], cwd: Path) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                raise RuntimeError(f"{self.name} already running (pid {self._proc.pid})")
            ts = time.strftime("%H:%M:%S")
            self._lines = [f"[{ts}] Starting: {' '.join(cmd)}"]
            self.start_time = time.time()
            self.exit_code = None
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        threading.Thread(target=self._read, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _read(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            with self._lock:
                self._lines.append(line.rstrip())
                if len(self._lines) > self._maxlines:
                    self._lines = self._lines[-self._maxlines:]
        proc.wait()
        with self._lock:
            self.exit_code = proc.returncode
            ts = time.strftime("%H:%M:%S")
            self._lines.append(f"[{ts}] Process exited (code {proc.returncode})")

    def logs_since(self, idx: int) -> dict:
        with self._lock:
            total = len(self._lines)
            start = max(0, min(idx, total))
            chunk = list(self._lines[start:])
        return {"lines": chunk, "next_index": start + len(chunk)}

    def status(self) -> dict:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            pid = self._proc.pid if self._proc else None
        return {
            "running": running,
            "pid": pid,
            "start_time": self.start_time,
            "exit_code": self.exit_code,
        }


BOT = ManagedProcess("bot")
BACKTEST = ManagedProcess("backtest")


# ── command builders ───────────────────────────────────────────────────────────

def _py() -> str:
    return sys.executable or "python"


def _bot_cmd(p: dict) -> tuple[List[str], Path]:
    return (
        [
            _py(),
            str(PROJECT_ROOT / "trading_bot" / "avvia_bot_live.py"),
            "--mode", "paper-live",
            "--symbols", p.get("symbol", "BTC/USDT"),
            "--timeframe", p.get("timeframe", "5m"),
            "--cost-model", p.get("cost_model", "conservative"),
            "--max-cycles", "0",
            "--poll-seconds", str(int(p.get("poll_seconds", 20))),
            "--no-cycle-artifacts",
        ],
        PROJECT_ROOT,
    )


def _backtest_cmd(p: dict) -> tuple[List[str], Path]:
    return (
        [
            _py(),
            str(PROJECT_ROOT / "trading_bot" / "run_custom_backtest.py"),
            "--balance", str(p.get("capital", 100)),
            "--candles", str(int(p.get("candles", 5000))),
        ],
        PROJECT_ROOT,
    )


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._html(WEB_DIR / "index.html")
        elif path == "/api/status":
            self._json({"bot": BOT.status(), "backtest": BACKTEST.status()})
        elif path == "/api/bot/logs":
            self._json(BOT.logs_since(int(qs.get("since", ["0"])[0])))
        elif path == "/api/backtest/logs":
            self._json(BACKTEST.logs_since(int(qs.get("since", ["0"])[0])))
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.rstrip("/")
        body = self._body()

        if path == "/api/bot/start":
            try:
                BOT.start(*_bot_cmd(body))
                self._json({"ok": True})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 409)
        elif path == "/api/bot/stop":
            BOT.stop()
            self._json({"ok": True})
        elif path == "/api/backtest/start":
            try:
                BACKTEST.start(*_backtest_cmd(body))
                self._json({"ok": True})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 409)
        elif path == "/api/backtest/stop":
            BACKTEST.stop()
            self._json({"ok": True})
        else:
            self.send_error(404)


def main() -> None:
    import webbrowser
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"ProgettoTR dashboard  →  {url}")
    print("CTRL+C to stop the dashboard server.\n")
    threading.Timer(0.9, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping subprocesses...")
        BOT.stop()
        BACKTEST.stop()
        print("Dashboard stopped.")


if __name__ == "__main__":
    main()
