"""Two days of synthetic feeds from two sources. Run: python3 demo.py"""
import json, os, tempfile
from pathlib import Path

from dealspotter import feed
from dealspotter.models import Criteria
from dealspotter.monitor import deliver, process
from dealspotter.store import Store


def L(i, title, make, model, year, km, price, region):
    return {"id": i, "title": title, "make": make, "model": model, "year": year, "km": km,
            "price": price, "region": region, "url": f"https://example.invalid/{i}"}


DAY1_A = {"source": "dealer-feed-A", "listings": [
    L("A1", "VW Golf 1.5 TSI", "VW", "Golf", 2020, 89000, "13 200", "Potsdam"),
    L("A2", "Skoda Octavia 2.0 TDI", "Skoda", "Octavia", 2019, 101000, 11500, "Berlin"),
    L("A3", "VW Golf 1.0 TSI", "VW", "Golf", 2017, 70000, 9900, "Berlin"),      # too old
    L("A4", "VW Golf 1.6 TDI", "VW", "Golf", 2019, 96500, 10900, "Potsdam"),
    L("A6", "Skoda Octavia 1.6 TDI", "Skoda", "Octavia", 2018, None, 9800, "Berlin"),  # km unknown
    {"id": "A5", "title": "VW Golf", "make": "VW", "model": "Golf", "price": "auf Anfrage"},  # unreadable
]}
DAY2_A = {"source": "dealer-feed-A", "listings": [
    L("A1", "VW Golf 1.5 TSI", "VW", "Golf", 2020, 89000, "11 900", "Potsdam"),  # price drop into limit
    L("A2", "Skoda Octavia 2.0 TDI", "Skoda", "Octavia", 2019, 101000, 11500, "Berlin"),
    L("A4", "VW Golf 1.6 TDI", "VW", "Golf", 2019, 96500, 10900, "Potsdam"),
]}
DAY2_B = {"source": "partner-feed-B", "listings": [
    L("B7", "Golf 1.6 TDI Comfortline", "VW", "Golf", 2019, 96000, 10700, "Potsdam"),  # possibly A4
]}


def main(lang="en"):
    tmp = Path(tempfile.mkdtemp())
    db = Store(str(tmp / "demo.db"))
    c = Criteria.from_dict(json.loads(Path("criteria_demo.json").read_text(encoding="utf-8")))
    sent = []
    for day, feeds in (("DAY 1", [DAY1_A]), ("DAY 2", [DAY2_A, DAY2_B])):
        print(f"\n=== {day} ===")
        for f in feeds:
            good, bad = feed.parse(f)
            for rid, why in bad:
                print(f"skipped {f['source']}#{rid}: {why}")
            process(good, c, db, lang)
        ok, _ = deliver(db, lambda t: (sent.append(t), print("->", t)))
        if day == "DAY 1":
            db.set_status("dealer-feed-A|A2", "to_contact")
    db.close()


if __name__ == "__main__":
    main()
