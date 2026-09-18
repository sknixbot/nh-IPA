from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from auth import get_access_token
from portfolio import fetch_account_list, call_nh_rest_api, _extract_domestic_account_body, DOMESTIC_BALANCE_PATH

OUT=Path("output/account_holdings_0918b.json")

def token_value():
    data=get_access_token()
    return data.get("access_token") if isinstance(data,dict) else data

def main():
    token=token_value()
    if not token: raise RuntimeError("NH access token unavailable")
    accounts=fetch_account_list(token)
    if not accounts: raise RuntimeError("NH account list unavailable")
    raw=[]
    for idx,account in enumerate(accounts):
        try:
            payload=call_nh_rest_api(token,DOMESTIC_BALANCE_PATH,_extract_domestic_account_body(account))
            raw.append({"account_index":idx,"payload":payload})
        except Exception as exc:
            raw.append({"account_index":idx,"error":type(exc).__name__})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),"account_count":len(accounts),"domestic_raw":raw},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"prepared account_count={len(accounts)}")
if __name__=="__main__": main()
