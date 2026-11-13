"""Spot the same car offered on several sources. Flag it; never hide it."""
from __future__ import annotations

from .models import Listing


def possible_duplicates(a: Listing, others: list[Listing]) -> list[Listing]:
    out = []
    for b in others:
        if b.source == a.source:
            continue  # same source: the listing id is the identity
        if (a.make.casefold(), a.model.casefold()) != (b.make.casefold(), b.model.casefold()):
            continue
        if a.year is None or b.year is None or a.year != b.year:
            continue
        if a.km is None or b.km is None or abs(a.km - b.km) > max(1000, int(0.02 * max(a.km, b.km))):
            continue
        if a.region.casefold() != b.region.casefold():
            continue
        if abs(a.price - b.price) > a.price * 5 / 100:
            continue
        out.append(b)
    return out
