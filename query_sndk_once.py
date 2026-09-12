from __future__ import annotations

import json
from pathlib import Path

from auth import get_access_token
from portfolio import fetch_account_list, fetch_overseas_holdings


def main() -> None:
    token_data = get_access_token()
    token = token_data.get("access_token") if isinstance(token_data, dict) else token_data
    if not token:
        raise RuntimeError("access_token 없음")

    matches = []
    for account in fetch_account_list(token):
        try:
            positions = fetch_overseas_holdings(token, account_no=account)
        except Exception:
            continue
        for position in positions:
            code = str(position.get("code") or "").upper()
            name = str(position.get("name") or "").upper()
            if code == "SNDK" or "SANDISK" in name:
                matches.append(
                    {
                        "code": code,
                        "name": position.get("name") or "",
                        "quantity": position.get("quantity", 0),
                        "avg_price": position.get("avg_price", 0),
                    }
                )

    Path("output").mkdir(exist_ok=True)
    Path("output/sndk.json").write_text(
        json.dumps({"matches": matches}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
