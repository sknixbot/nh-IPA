
import argparse
import asyncio
import os
from pathlib import Path

from alerts import alert_status_rows
from monitor import monitor
from export_excel import export
from portfolio import load_watchlist, refresh_watchlist_from_state


def codes():
    p = Path("config/watchlist.txt")
    if not p.exists():
        return []
    return [
        x.strip()
        for x in p.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def sync_watchlist_if_configured():
    configured = bool(
        os.getenv("NH_DOMESTIC_HOLDINGS_URL") or os.getenv("NH_OVERSEAS_HOLDINGS_URL")
    )
    if not configured:
        return codes()
    refreshed = refresh_watchlist_from_state()
    return refreshed if refreshed else codes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--sync-watchlist", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        print("SELFTEST OK")
        print("감시종목:", sync_watchlist_if_configured())
        return

    if args.status:
        for row in alert_status_rows():
            print(f"{row['유형']}: {row['상태']}")
        return

    if args.sync_watchlist:
        refreshed = sync_watchlist_if_configured()
        print("동기화된 감시종목:", refreshed)
        return

    active_codes = sync_watchlist_if_configured()
    asyncio.run(monitor(active_codes, args.minutes * 60))
    export()


if __name__ == "__main__":
    main()
