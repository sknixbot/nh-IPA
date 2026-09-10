import argparse
import asyncio
from pathlib import Path

from alerts import alert_status_rows
from monitor import monitor
from export_excel import export
from portfolio import (
    load_watchlist,
    refresh_watchlist_from_state,
)


def codes():
    path = Path("config/watchlist.txt")

    if not path.exists():
        return []

    return [
        x.strip()
        for x in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if x.strip()
    ]


def sync_account_watchlist():

    old_codes = codes()

    print(
        f"[기존 감시목록] "
        f"{len(old_codes)}종목"
    )

    try:

        refreshed = refresh_watchlist_from_state()

        if refreshed:

            print(
                f"[계좌 동기화 성공] "
                f"{len(refreshed)}종목"
            )

            return refreshed

        print(
            "[계좌 동기화 결과 없음] "
            "기존 감시목록 유지"
        )

        return old_codes

    except Exception as e:

        print(
            f"[계좌 동기화 실패] "
            f"{type(e).__name__}: {e}"
        )

        print(
            "[보호동작] 기존 감시목록 유지"
        )

        return old_codes


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--minutes",
        type=int,
        default=10
    )

    parser.add_argument(
        "--selftest",
        action="store_true"
    )

    parser.add_argument(
        "--status",
        action="store_true"
    )

    parser.add_argument(
        "--sync-watchlist",
        action="store_true"
    )

    args = parser.parse_args()

    if args.selftest:

        print("SELFTEST OK")

        active_codes = sync_account_watchlist()

        print(
            "감시종목:",
            active_codes
        )

        return

    if args.status:

        for row in alert_status_rows():

            print(
                f"{row['유형']}: "
                f"{row['상태']}"
            )

        return

    active_codes = sync_account_watchlist()

    if args.sync_watchlist:

        print(
            "동기화된 감시종목:",
            active_codes
        )

        return

    if not active_codes:

        raise RuntimeError(
            "계좌 보유종목과 기존 watchlist 모두 없습니다."
        )

    asyncio.run(
        monitor(
            active_codes,
            args.minutes * 60,
            max_retries=5
        )
    )

    export()


if __name__ == "__main__":
    main()
