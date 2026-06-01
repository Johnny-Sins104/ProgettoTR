from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.core.lsr_v2_telegram_notification_bridge import (  # noqa: E402
    REQUIRED_CONFIRMATION,
    LSRV2TelegramNotificationBridgeSettings,
    run_lsr_v2_telegram_notification_bridge,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 Telegram notification bridge / supervised paper trade alerts")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--send", action="store_true", help="Attempt real Telegram send; still requires confirmation and token/chat ID.")
    parser.add_argument("--confirmation", default="", help=f"Required phrase: {REQUIRED_CONFIRMATION}")
    parser.add_argument("--force-resend", action="store_true", help="Ignore sent notification state and resend selected messages.")
    parser.add_argument("--max-messages", type=int, default=5)
    args = parser.parse_args()

    env_settings = LSRV2TelegramNotificationBridgeSettings.from_env(data_dir=args.data_dir)
    settings = LSRV2TelegramNotificationBridgeSettings(
        **{
            **env_settings.to_dict(),
            "data_dir": args.data_dir,
            "send_enable": "1" if args.send else env_settings.send_enable,
            "send_confirmation": args.confirmation or env_settings.send_confirmation,
            "force_resend": bool(args.force_resend or env_settings.force_resend),
            "max_messages": int(args.max_messages or env_settings.max_messages),
            "telegram_token": env_settings.telegram_token,
        }
    )
    report = run_lsr_v2_telegram_notification_bridge(data_dir=args.data_dir, settings=settings)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
