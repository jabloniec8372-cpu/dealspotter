"""SQLite state: seen listings, client status, alert outbox."""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Optional

from .models import Listing

STATUSES = ("nowe", "do_kontaktu", "sprawdzone", "odrzucone")


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS listings(
              key TEXT PRIMARY KEY, data TEXT NOT NULL, price TEXT NOT NULL,
              matched INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'nowe');
            CREATE TABLE IF NOT EXISTS outbox(
              key TEXT PRIMARY KEY, text TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
            """
        )

    def get(self, key: str) -> Optional[tuple[Decimal, bool, str]]:
        r = self.db.execute("SELECT price, matched, status FROM listings WHERE key=?", (key,)).fetchone()
        return (Decimal(r[0]), bool(r[1]), r[2]) if r else None

    def save(self, l: Listing, matched: bool) -> None:
        """Insert or update. The client's status is never touched by a read."""
        data = json.dumps({**l.__dict__, "price": str(l.price)})
        self.db.execute(
            "INSERT INTO listings(key,data,price,matched) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET data=excluded.data, price=excluded.price, matched=excluded.matched",
            (l.key, data, str(l.price), int(matched)),
        )
        self.db.commit()

    def all_listings(self) -> list[Listing]:
        out = []
        for (data,) in self.db.execute("SELECT data FROM listings"):
            d = json.loads(data)
            d["price"] = Decimal(d["price"])
            out.append(Listing(**d))
        return out

    def set_status(self, key: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if self.db.execute("UPDATE listings SET status=? WHERE key=?", (status, key)).rowcount == 0:
            raise KeyError(key)
        self.db.commit()

    def queue(self, key: str, text: str) -> bool:
        """Write an alert to the outbox once. False if it already exists."""
        cur = self.db.execute("INSERT OR IGNORE INTO outbox(key,text) VALUES(?,?)", (key, text))
        self.db.commit()
        return cur.rowcount == 1

    def pending(self) -> list[tuple[str, str]]:
        return self.db.execute("SELECT key, text FROM outbox WHERE sent=0 ORDER BY rowid").fetchall()

    def mark_sent(self, key: str) -> None:
        self.db.execute("UPDATE outbox SET sent=1 WHERE key=?", (key,))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
