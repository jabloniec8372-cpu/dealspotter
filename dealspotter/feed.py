"""Read listings from a JSON feed (a dealer/partner export or an official API).

This tool deliberately does NOT scrape portals such as mobile.de or AutoScout24:
their terms forbid it. Use a feed you are allowed to read. The reader returns
the listings it could parse AND the rows it could not, with the reason, so
nothing disappears silently.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Listing


def _price(v) -> Decimal:
    if isinstance(v, (int, float)):
        d = Decimal(str(v))
    else:
        s = str(v).replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "").strip()
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
            s = s.replace(".", "")  # 13.200 -> 13200
        d = Decimal(s)
    if d <= 0:
        raise InvalidOperation("price must be positive")
    return d


def _int_or_none(v):
    if v in (None, ""):
        return None
    return int(str(v).replace(" ", "").replace(".", ""))


def parse(data: dict) -> tuple[list[Listing], list[tuple[str, str]]]:
    source = data.get("source", "feed")
    good, bad = [], []
    for row in data.get("listings", []):
        rid = str(row.get("id", "?"))
        try:
            good.append(
                Listing(
                    source=source,
                    listing_id=str(row["id"]),
                    title=row["title"],
                    make=row["make"],
                    model=row["model"],
                    year=_int_or_none(row.get("year")),
                    km=_int_or_none(row.get("km")),
                    price=_price(row["price"]),
                    region=row.get("region", ""),
                    url=row.get("url", ""),
                )
            )
        except (KeyError, ValueError, InvalidOperation) as e:
            bad.append((rid, "row could not be read: " + ("missing field " + str(e) if isinstance(e, KeyError) else "invalid price or number")))
    return good, bad


def load(path) -> tuple[list[Listing], list[tuple[str, str]]]:
    return parse(json.loads(Path(path).read_text(encoding="utf-8")))
