import sqlite3
import json
from pathlib import Path


class DatabaseManager:

    def __init__(self, db_path: str = "data/trading_bot.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol    TEXT,
                verdict   TEXT,
                score     INTEGER,
                entry     REAL,
                sl        REAL,
                tp        REAL,
                logs      TEXT
            )
        """)
        self.conn.commit()

    def save_trade(self, data: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO trades (timestamp, symbol, verdict, score, entry, sl, tp, logs)
            VALUES (:timestamp, :symbol, :verdict, :score, :entry, :sl, :tp, :logs)
            """,
            {**data, "logs": json.dumps(data.get("logs", []))},  # serializza la lista logs
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
