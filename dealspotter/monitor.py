"""One run: listings in, alerts queued; then deliver the outbox."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable

from .dupes import possible_duplicates
from .match import evaluate
from .models import Criteria, Listing
from .store import Store

CHECK_TEXT = {
    "NO_KM": "przebieg nieznany - sprawdź",
    "NO_YEAR": "rocznik nieznany - sprawdź",
}


def eur(p: Decimal) -> str:
    return f"{int(p):,}".replace(",", " ") + " €"


def describe(l: Listing) -> str:
    parts = [l.title]
    if l.year:
        parts.append(str(l.year))
    parts.append(f"{l.km // 1000} tys. km" if l.km is not None else "przebieg ?")
    parts.append(l.region)
    return ", ".join(parts)


@dataclass
class Result:
    queued: int = 0
    seen: int = 0
    skipped_rejected: int = 0
    unreadable: list = field(default_factory=list)


def process(listings: Iterable[Listing], c: Criteria, store: Store) -> Result:
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
        limit = f" i mieści się w Twoim limicie {eur(c.max_price)}" if c.max_price is not None else ""
        if event == "DROP":
            text = f"{describe(l)}. Cena spadła z {eur(prev[0])} do {eur(l.price)}{limit}."
        elif event == "NOW_MATCHES":
            text = f"{describe(l)}. Teraz pasuje do kryteriów: {eur(l.price)}{limit}."
        else:
            text = f"{describe(l)}. Nowe ogłoszenie: {eur(l.price)}{limit}."
        for chk in m.checks:
            text += f" UWAGA: {CHECK_TEXT[chk]}."
        dups = possible_duplicates(l, store.all_listings())
        for d in dups:
            text += f" Możliwy duplikat: {d.source} #{d.listing_id} za {eur(d.price)} (sprawdź, to może być to samo auto)."
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
