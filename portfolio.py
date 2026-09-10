def refresh_watchlist_from_state():

    old_watchlist = load_watchlist()

    try:
        token_data = get_access_token()
    except Exception as e:

        print(
            f"[인증 실패] "
            f"{type(e).__name__}: {e}"
        )

        return old_watchlist

    if isinstance(token_data, dict):
        token = token_data.get(
            "access_token"
        )
    else:
        token = token_data

    if not token:

        print(
            "[인증 실패] "
            "access_token 없음"
        )

        return old_watchlist

    domestic_account_no = (
        os.getenv(
            "NH_DOMESTIC_ACCOUNT_NO"
        )
        or os.getenv(
            "NH_ACCOUNT_NO"
        )
    )

    overseas_account_no = (
        os.getenv(
            "NH_OVERSEAS_ACCOUNT_NO"
        )
        or os.getenv(
            "NH_ACCOUNT_NO"
        )
    )

    try:

        accounts = fetch_account_list(token)

        if not domestic_account_no:
            domestic_accounts = accounts
        else:
            domestic_accounts = [
                domestic_account_no
            ]

        if not overseas_account_no:
            overseas_accounts = accounts
        else:
            overseas_accounts = [
                overseas_account_no
            ]

        positions = []

        for account in domestic_accounts:

            try:

                holdings = (
                    fetch_domestic_holdings(
                        token,
                        account_no=account
                    )
                )

                positions.extend(
                    holdings
                )

            except Exception as e:

                print(
                    f"[국내잔고 조회 실패] "
                    f"{mask_account_no(account)} "
                    f"{type(e).__name__}: {e}"
                )

        for account in overseas_accounts:

            try:

                holdings = (
                    fetch_overseas_holdings(
                        token,
                        account_no=account
                    )
                )

                positions.extend(
                    holdings
                )

            except Exception as e:

                print(
                    f"[해외잔고 조회 실패] "
                    f"{mask_account_no(account)} "
                    f"{type(e).__name__}: {e}"
                )

        new_codes = (
            build_watchlist_from_positions(
                positions
            )
        )

        if not new_codes:

            print(
                "[계좌조회 결과 보유종목 없음 또는 조회 실패] "
                "기존 watchlist를 유지합니다."
            )

            return old_watchlist

        sync_watchlist_from_positions(
            positions
        )

        print(
            f"[계좌 보유종목 동기화] "
            f"{len(new_codes)}종목"
        )

        return new_codes

    except Exception as e:

        print(
            f"[계좌조회 실패] "
            f"{type(e).__name__}: {e}"
        )

        return old_watchlist
        
        def load_watchlist(path=WATCHLIST_PATH):
    if not path.exists():
        return []

    return [
        x.strip()
        for x in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if x.strip()
    ]