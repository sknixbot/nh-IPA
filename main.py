
import argparse
import asyncio
from pathlib import Path

from alerts import alert_status_rows
from monitor import monitor
from export_excel import export


def codes():
    p = Path("config/watchlist.txt")
    if not p.exists():
        return []
    return [
        x.strip()
        for x in p.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        print("SELFTEST OK")
        print("감시종목:", codes())
        return

    if args.status:
        for row in alert_status_rows():
            print(f"{row['유형']}: {row['상태']}")
        return

    asyncio.run(monitor(codes(), args.minutes * 60))
    export()


if __name__ == "__main__":
    main()
