"""Data model."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class Listing:
    source: str
    listing_id: str
    title: str
    make: str
    model: str
    year: Optional[int]
    km: Optional[int]  # None = the feed did not say; never guessed
    price: Decimal
    region: str
    url: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}|{self.listing_id}"


@dataclass
class Criteria:
    """What the client wants. A rule left empty is not checked."""

    models: list[str] = field(default_factory=list)  # "vw golf": casefolded "make model" prefixes
    max_price: Optional[Decimal] = None
    min_year: Optional[int] = None
    max_km: Optional[int] = None
    regions: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "Criteria":
        mp = d.get("max_price")
        return Criteria(
            models=[m.casefold() for m in d.get("models", [])],
            max_price=Decimal(str(mp)) if mp is not None else None,
            min_year=d.get("min_year"),
            max_km=d.get("max_km"),
            regions=[r.casefold() for r in d.get("regions", [])],
        )
