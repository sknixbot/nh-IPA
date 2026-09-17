from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from auth import get_access_token
from portfolio import (
    fetch_account_list,
    fetch_domestic_holdings,
    fetch_overseas_holdings,
)

OUTPUT = Path("output/account_holdings.json")


def _token_value():
    token_data = get_access_token()
    if isinstance(token_data, dict):
        return token_data.get("access_token")
    return token_data


def _dedupe(rows):
    seen = set()
    result = []
    for row in rows:
        item = {
            "code": str(row.get("code") or "").strip(),
            "name": str(row.get("name") or "").strip(),
            "quantity": int(row.get("quantity") or 0),
            "avg_price": float(row.get("avg_price") or 0),
        }
        key = (item["code"], item["quantity"], item["avg_price"])
        if not item["code"] or item["quantity"] <= 0 or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    token = _token_value()
    if not token:
        raise RuntimeError("NH access token unavailable")

    accounts = fetch_account_list(token)
    if not accounts:
        raise RuntimeError("NH account list unavailable")

    domestic = []
    overseas = []
    errors = []

    for account in accounts:
        try:
            domestic.extend(fetch_domestic_holdings(token, account_no=account))
        except Exception as exc:
            errors.append(f"domestic:{type(exc).__name__}")
        try:
            overseas.extend(fetch_overseas_holdings(token, account_no=account))
        except Exception as exc:
            errors.append(f"overseas:{type(exc).__name__}")

    domestic = _dedupe(domestic)
    overseas = _dedupe(overseas)
    if not domestic and not overseas:
        raise RuntimeError("No holdings returned: " + ",".join(errors))

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "domestic": domestic,
        "overseas": overseas,
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Encrypted export source prepared: domestic={len(domestic)}, overseas={len(overseas)}")


if __name__ == "__main__":
    main()
