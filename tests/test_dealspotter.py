import json
import unittest
from decimal import Decimal

from dealspotter import feed
from dealspotter.dupes import possible_duplicates
from dealspotter.match import evaluate
from dealspotter.models import Criteria, Listing
from dealspotter.monitor import deliver, process
from dealspotter.store import Store
from dealspotter.telegram import make_sender

C = Criteria.from_dict({"models": ["vw golf"], "max_price": 12000, "min_year": 2018, "max_km": 120000, "regions": ["Potsdam"]})


def car(i="1", price=11000, km=80000, year=2020, region="Potsdam", source="A", model="Golf"):
    return Listing(source, i, f"VW {model}", "VW", model, year, km, Decimal(price), region, "")


class FeedTests(unittest.TestCase):
    def test_price_formats(self):
        for raw, want in (("13 200", 13200), ("13.200 €", 13200), ("12.999,50", Decimal("12999.50")), (11900, 11900)):
            self.assertEqual(feed._price(raw), Decimal(str(want)))

    def test_bad_rows_are_reported_not_dropped_silently(self):
        good, bad = feed.parse({"source": "S", "listings": [
            {"id": "1", "title": "t", "make": "VW", "model": "Golf", "price": "auf Anfrage"},
            {"id": "2", "title": "t", "make": "VW", "model": "Golf", "price": 0},
            {"id": "3", "title": "t", "make": "VW", "price": 5000},
            {"id": "4", "title": "t", "make": "VW", "model": "Golf", "price": 5000}]})
        self.assertEqual([g.listing_id for g in good], ["4"])
        self.assertEqual([b[0] for b in bad], ["1", "2", "3"])


class MatchTests(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(evaluate(car(), C).ok)
        self.assertFalse(evaluate(car(price=12001), C).ok)
        self.assertFalse(evaluate(car(year=2017), C).ok)
        self.assertFalse(evaluate(car(km=120001), C).ok)
        self.assertFalse(evaluate(car(region="Berlin"), C).ok)
        self.assertFalse(evaluate(car(model="Polo"), C).ok)

    def test_unknown_km_is_flagged_not_assumed(self):
        m = evaluate(car(km=None), C)
        self.assertTrue(m.ok)
        self.assertEqual(m.checks, ["NO_KM"])


class DupeTests(unittest.TestCase):
    def test_same_car_other_source(self):
        a, b = car("1", 10900, 96500, source="A"), car("9", 10700, 96000, source="B")
        self.assertEqual(possible_duplicates(b, [a]), [a])

    def test_not_duplicate(self):
        a = car("1", 10900, 96500, source="A")
        self.assertEqual(possible_duplicates(car("9", 10700, 60000, source="B"), [a]), [])
        self.assertEqual(possible_duplicates(car("9", 7000, 96000, source="B"), [a]), [])
        self.assertEqual(possible_duplicates(car("9", 10700, 96000, source="A"), [a]), [])  # same source
        self.assertEqual(possible_duplicates(car("9", 10700, None, source="B"), [a]), [])  # unknown km: no claim


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.addCleanup(self.s.close)

    def test_new_then_quiet_then_drop(self):
        self.assertEqual(process([car(price=11500)], C, self.s).queued, 1)
        self.assertEqual(process([car(price=11500)], C, self.s).queued, 0)
        r = process([car(price=11000)], C, self.s)
        self.assertEqual(r.queued, 1)
        self.assertIn("Price dropped from 11 500 € to 11 000 €", self.s.pending()[-1][1])

    def test_price_rise_is_silent(self):
        process([car(price=11000)], C, self.s)
        self.assertEqual(process([car(price=11500)], C, self.s).queued, 0)

    def test_drop_into_limit(self):
        self.assertEqual(process([car(price=13200)], C, self.s).queued, 0)
        self.assertEqual(process([car(price=11900)], C, self.s).queued, 1)
        self.assertIn("dropped from 13 200 € to 11 900 €", self.s.pending()[0][1])

    def test_status_survives_reads_and_rejected_stays_quiet(self):
        process([car(price=11500)], C, self.s)
        self.s.set_status("A|1", "odrzucone")
        self.assertEqual(process([car(price=10000)], C, self.s).queued, 0)
        self.assertEqual(self.s.get("A|1")[2], "odrzucone")
        process([car(i="2")], C, self.s)
        self.s.set_status("A|2", "do_kontaktu")
        process([car(i="2", price=10500)], C, self.s)
        self.assertEqual(self.s.get("A|2")[2], "do_kontaktu")

    def test_unknown_status_rejected(self):
        process([car()], C, self.s)
        with self.assertRaises(ValueError):
            self.s.set_status("A|1", "kupione")
        with self.assertRaises(KeyError):
            self.s.set_status("A|404", "nowe")

    def test_duplicate_is_flagged_in_alert_but_not_suppressed(self):
        process([car("1", 10900, 96500, source="A")], C, self.s)
        process([car("9", 10700, 96000, source="B")], C, self.s)
        texts = [t for _, t in self.s.pending()]
        self.assertEqual(len(texts), 2)
        self.assertIn("Possible duplicate: A #1", texts[1])

    def test_polish_alert_texts_still_available(self):
        process([car(price=11500)], C, self.s, "pl")
        process([car(price=11000)], C, self.s, "pl")
        self.assertIn("Cena spadła z 11 500 € do 11 000 €", self.s.pending()[-1][1])

    def test_english_status_names_map_to_stored_ones(self):
        process([car(price=11500)], C, self.s)
        self.s.set_status("A|1", "rejected")
        self.assertEqual(self.s.get("A|1")[2], "odrzucone")
        self.assertEqual(process([car(price=10000)], C, self.s).queued, 0)

    def test_unknown_km_warning_in_alert(self):
        process([car(km=None)], C, self.s)
        self.assertIn("mileage unknown", self.s.pending()[0][1])


class DeliveryTests(unittest.TestCase):
    def test_failed_send_stays_pending_and_is_retried(self):
        s = Store()
        process([car("1"), car("2")], C, s)
        calls = []

        def flaky(text):
            calls.append(text)
            if "Golf" in text and len(calls) == 1:
                raise RuntimeError("down")

        self.assertEqual(deliver(s, flaky), (1, 1))
        self.assertEqual(len(s.pending()), 1)
        self.assertEqual(deliver(s, lambda t: None), (1, 0))
        self.assertEqual(s.pending(), [])

    def test_no_duplicate_alert_after_delivery(self):
        s = Store()
        process([car()], C, s)
        deliver(s, lambda t: None)
        self.assertEqual(process([car()], C, s).queued, 0)

    def test_telegram_sender(self):
        seen = []
        send = make_sender("T", "42", post=lambda url, body: (seen.append((url, body)), {"ok": True})[1])
        send("hi")
        self.assertEqual(seen[0][1], {"chat_id": "42", "text": "hi"})
        with self.assertRaises(RuntimeError):
            make_sender("T", "42", post=lambda u, b: {"ok": False})("x")


class DemoTest(unittest.TestCase):
    def test_demo_runs(self):
        import contextlib, io, demo
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            demo.main()
        out = buf.getvalue()
        self.assertIn("Price dropped from 13 200 € to 11 900 €", out)
        self.assertIn("Possible duplicate", out)
        self.assertIn("mileage unknown", out)
        self.assertIn("skipped dealer-feed-A#A5", out)


if __name__ == "__main__":
    unittest.main()
