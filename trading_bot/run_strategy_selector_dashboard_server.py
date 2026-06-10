from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.dashboard.strategy_dashboard_api import get_strategy_status, post_strategy_calibrate, post_strategy_select


DASHBOARD_HTML = Path(__file__).resolve().parent / "dashboard" / "strategy_selector_dashboard.html"


def make_handler(data_dir: Path):
    class StrategyDashboardHandler(BaseHTTPRequestHandler):
        server_version = "ProgettoTRStrategyDashboard/0.1"

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, path: Path) -> None:
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path in {"/", "/dashboard", "/strategy-dashboard"}:
                self._html(DASHBOARD_HTML)
                return
            if self.path == "/api/strategy/status":
                self._json(get_strategy_status(data_dir))
                return
            self._json({"status": "NOT_FOUND", "reason": "unknown_route"}, status=404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            payload = self._read_payload()
            if self.path == "/api/strategy/select":
                result = post_strategy_select(payload, data_dir)
                status = 200 if result.get("status") == "OK" else 409
                self._json(result, status=status)
                return
            if self.path == "/api/strategy/calibrate":
                result = post_strategy_calibrate(payload, data_dir)
                status = 200 if result.get("status") == "OK" else 400
                self._json(result, status=status)
                return
            self._json({"status": "NOT_FOUND", "reason": "unknown_route"}, status=404)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[strategy-dashboard] {self.address_string()} {format % args}", flush=True)

    return StrategyDashboardHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only strategy selector dashboard locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Path(args.data_dir)))
    print(f"Strategy selector dashboard: http://{args.host}:{args.port}/dashboard")
    print("Read-only/fail-closed preflight. Press CTRL+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping strategy selector dashboard.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
