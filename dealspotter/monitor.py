"""One run: listings in, alerts queued; then deliver the outbox."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable

from .dupes import possible_duplicates
from .match import evaluate
from .models import Criteria, Listing
from .store import Store

TEXT = {
    "en": {
        "NO_KM": "mileage unknown - please check",
        "NO_YEAR": "year unknown - please check",
        "km": "{n}k km", "km_unknown": "mileage ?",
        "limit": " and within your limit of {p}",
        "DROP": "{d}. Price dropped from {old} to {new}{limit}.",
        "NOW_MATCHES": "{d}. Now matches your criteria: {new}{limit}.",
        "NEW": "{d}. New listing: {new}{limit}.",
        "check": " CHECK: {t}.",
        "dup": " Possible duplicate: {src} #{id} for {p} (please check, it may be the same car).",
    },
    "pl": {
        "NO_KM": "przebieg nieznany - sprawdź",
        "NO_YEAR": "rocznik nieznany - sprawdź",
        "km": "{n} tys. km", "km_unknown": "przebieg ?",
        "limit": " i mieści się w Twoim limicie {p}",
        "DROP": "{d}. Cena spadła z {old} do {new}{limit}.",
        "NOW_MATCHES": "{d}. Teraz pasuje do kryteriów: {new}{limit}.",
        "NEW": "{d}. Nowe ogłoszenie: {new}{limit}.",
        "check": " UWAGA: {t}.",
        "dup": " Możliwy duplikat: {src} #{id} za {p} (sprawdź, to może być to samo auto).",
    },
}


def eur(p: Decimal) -> str:
    return f"{int(p):,}".replace(",", " ") + " €"


def describe(l: Listing, lang: str = "en") -> str:
    t = TEXT[lang]
    parts = [l.title]
    if l.year:
        parts.append(str(l.year))
    parts.append(t["km"].format(n=l.km // 1000) if l.km is not None else t["km_unknown"])
    parts.append(l.region)
    return ", ".join(parts)


@dataclass
class Result:
    queued: int = 0
    seen: int = 0
    skipped_rejected: int = 0
    unreadable: list = field(default_factory=list)


def process(listings: Iterable[Listing], c: Criteria, store: Store, lang: str = "en") -> Result:
    t = TEXT[lang]
    res = Result()
    for l in listings:
        res.seen += 1
        m = evaluate(l, c)
        prev = store.get(l.key)
        store.save(l, m.ok)
        if prev and prev[2] == "odrzucone":
            res.skipped_rejected += 1
            continue  # the client dismissed it: stay quiet
        if not m.ok:
            continue
        event = None
        if prev is None:
            event = "NEW"
        elif l.price < prev[0]:
            event = "DROP"
        elif not prev[1]:
            event = "NOW_MATCHES"
        if event is None:
            continue
        limit = t["limit"].format(p=eur(c.max_price)) if c.max_price is not None else ""
        old = eur(prev[0]) if prev else ""
        text = t[event].format(d=describe(l, lang), old=old, new=eur(l.price), limit=limit)
        for chk in m.checks:
            text += t["check"].format(t=t[chk])
        dups = possible_duplicates(l, store.all_listings())
        for d in dups:
            text += t["dup"].format(src=d.source, id=d.listing_id, p=eur(d.price))
        if l.url:
            text += f" {l.url}"
        if store.queue(f"{l.key}|{event}|{l.price}", text):
            res.queued += 1
    return res


def deliver(store: Store, send: Callable[[str], None]) -> tuple[int, int]:
    """Send pending alerts; mark each as sent only after the channel accepted it."""
    ok = failed = 0
    for key, text in store.pending():
        try:
            send(text)
        except Exception:
            failed += 1
            continue
        store.mark_sent(key)
        ok += 1
    return ok, failed
