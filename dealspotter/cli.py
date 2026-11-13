"""python -m dealspotter run|status|pending"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import feed
from .models import Criteria
from .monitor import deliver, process
from .store import STATUS_CHOICES, Store
from .telegram import make_sender


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dealspotter")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--criteria", required=True)
    r.add_argument("--feed", required=True, nargs="+")
    r.add_argument("--db", default="dealspotter.db")
    r.add_argument("--lang", choices=("en", "pl"), default="en", help="language of the alert texts")
    r.add_argument("--telegram", action="store_true", help="needs TELEGRAM_TOKEN and TELEGRAM_CHAT_ID")
    s = sub.add_parser("status", help="set the client's status of a listing")
    s.add_argument("key", help="source|id")
    s.add_argument("status", choices=STATUS_CHOICES)
    s.add_argument("--db", default="dealspotter.db")
    args = p.parse_args(argv)

    store = Store(args.db)
    if args.cmd == "status":
        store.set_status(args.key, args.status)
        print(f"{args.key} -> {args.status}")
        return 0
    c = Criteria.from_dict(json.loads(Path(args.criteria).read_text(encoding="utf-8")))
    total = 0
    for f in args.feed:
        good, bad = feed.load(f)
        for rid, why in bad:
            print(f"skipped {f}#{rid}: {why}")
        total += process(good, c, store, args.lang).queued
    if args.telegram:
        send = make_sender(os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
        ok, failed = deliver(store, send)
        print(f"{total} new alert(s); sent {ok}, failed {failed} (failed ones stay in the outbox)")
        return 1 if failed else 0
    for _, text in store.pending():
        print("-", text)
    print(f"{total} new alert(s) in the outbox")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
