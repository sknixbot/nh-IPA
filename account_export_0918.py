from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from auth import get_access_token
from portfolio import fetch_account_list, fetch_domestic_holdings, fetch_overseas_holdings

OUT=Path("output/account_holdings_0918.json")

def token_value():
    data=get_access_token()
    return data.get("access_token") if isinstance(data,dict) else data

def clean(rows):
    out=[]; seen=set()
    for r in rows:
        item={"code":str(r.get("code") or "").strip(),"name":str(r.get("name") or "").strip(),
              "quantity":int(r.get("quantity") or 0),"avg_price":float(r.get("avg_price") or 0)}
        key=(item["code"],item["quantity"],item["avg_price"])
        if item["code"] and item["quantity"]>0 and key not in seen:
            seen.add(key); out.append(item)
    return out

def main():
    token=token_value()
    if not token: raise RuntimeError("NH access token unavailable")
    accounts=fetch_account_list(token)
    if not accounts: raise RuntimeError("NH account list unavailable")
    domestic=[]; overseas=[]; errors=[]
    for account in accounts:
        try: domestic.extend(fetch_domestic_holdings(token,account_no=account))
        except Exception as exc: errors.append("domestic:"+type(exc).__name__)
        try: overseas.extend(fetch_overseas_holdings(token,account_no=account))
        except Exception as exc: errors.append("overseas:"+type(exc).__name__)
    domestic=clean(domestic); overseas=clean(overseas)
    if not domestic and not overseas: raise RuntimeError("No holdings returned")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "domestic":domestic,"overseas":overseas,"errors":errors},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"prepared domestic={len(domestic)} overseas={len(overseas)}")
if __name__=="__main__": main()
