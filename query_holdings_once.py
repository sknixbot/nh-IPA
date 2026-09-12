from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from auth import get_access_token
from portfolio import fetch_account_list, fetch_domestic_holdings, fetch_overseas_holdings


def main() -> None:
    token_data = get_access_token()
    token = token_data.get("access_token") if isinstance(token_data, dict) else token_data
    if not token:
        raise RuntimeError("access_token 없음")

    positions = []
    for account in fetch_account_list(token):
        for fetcher, market in (
            (fetch_domestic_holdings, "KR"),
            (fetch_overseas_holdings, "US"),
        ):
            try:
                rows = fetcher(token, account_no=account)
            except Exception:
                continue
            for row in rows:
                positions.append({"market": market, **row})

    public_key = serialization.load_pem_public_key(
        Path("holdings_lookup_public.pem").read_bytes()
    )
    encrypted_lines = []
    for position in positions:
        raw = json.dumps(position, ensure_ascii=False, separators=(",", ":")).encode()
        encrypted = public_key.encrypt(
            raw,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        encrypted_lines.append(base64.b64encode(encrypted).decode())

    Path("output").mkdir(exist_ok=True)
    Path("output/holdings.enc").write_text(
        "\n".join(encrypted_lines) + ("\n" if encrypted_lines else ""),
        encoding="ascii",
    )


if __name__ == "__main__":
    main()
