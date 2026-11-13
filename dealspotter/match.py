"""Criteria matching with reasons. Unknown values are flagged, not assumed."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Criteria, Listing


@dataclass
class Match:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # things a human should verify


def evaluate(l: Listing, c: Criteria) -> Match:
    why, checks = [], []
    name = f"{l.make} {l.model}".casefold()
    if c.models and not any(name.startswith(m) for m in c.models):
        return Match(False)
    if c.max_price is not None:
        if l.price > c.max_price:
            return Match(False)
        why.append("price")
    if c.regions and l.region.casefold() not in c.regions:
        return Match(False)
    if c.min_year is not None:
        if l.year is None:
            checks.append("NO_YEAR")
        elif l.year < c.min_year:
            return Match(False)
    if c.max_km is not None:
        if l.km is None:
            checks.append("NO_KM")
        elif l.km > c.max_km:
            return Match(False)
    return Match(True, why, checks)
