from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

from auth import get_access_token

WATCHLIST_PATH = Path("config/watchlist.txt")
NH_API_BASE = "https://api.nhplug.com:8443"
ACCOUNT_LIST_PATH = "/n2/acctinfo"
DOMESTIC_BALANCE_PATH = "/krstock/inquiry/v1/balance"
OVERSEAS_BALANCE_PATH = "/gbstock/inquiry/v1/balance"
DOMESTIC_INVESTOR_PATH = "/krstock/quote/v1/currentInvestor"
OVERSEAS_QUOTE_PATH = "/gbstock/quote/v1/current"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def mask_account_no(account_no: str | None) -> str:
    if not account_no:
        return "********"
    text = str(account_no).strip()
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:3]}********{text[-2:]}"


def _coerce_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def _normalise_output1(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    for key in ("Output_1", "output_1", "output1"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    output = payload.get("output")
    if isinstance(output, dict):
        rslt = output.get("rslt")
        if isinstance(rslt, dict):
            items = rslt.get("items")
            if isinstance(items, list):
                return items
        items = output.get("items")
        if isinstance(items, list):
            return items

    if isinstance(payload.get("data"), list):
        return payload.get("data")
    return []


def _extract_domestic_account_body(account_no: str | None) -> Dict[str, Any]:
    if not account_no:
        return {}
    return {
        "act_no": account_no,
        "bnc_bse_cd": "1",
        "ltg_aot_dit_cd": "9",
        "aet_bse": "2",
        "qut_dit_cd": "UNT",
    }


def _extract_overseas_account_body(account_no: str | None) -> Dict[str, Any]:
    if not account_no:
        return {}
    return {
        "act_no": account_no,
        "qut_iqr_dit_cd": "9",
        "fc_sec_trd_nat_cd": "200",
        "cur_cd": "KRW",
        "xns_dit_cd": "0",
    }


def normalize_domestic_positions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """국내_주식_조회_잔고의 실제 공식 응답 예시 기반으로 표준화한다."""
    positions: List[Dict[str, Any]] = []
    items = _normalise_output1(payload)
    if not items:
        output = payload.get("output") if isinstance(payload, dict) else {}
        if isinstance(output, dict):
            items = output.get("rslt", {}).get("items", [])

    for item in items:
        code = str(item.get("iem_cd") or item.get("pdno") or item.get("code") or "").strip()
        if not code:
            continue
        quantity = _to_int(item.get("itg_bnc_qty") or item.get("rsdl_qty") or item.get("hldg_qty") or 0, 0)
        if quantity <= 0:
            continue
        avg_price = _to_float(item.get("phs_pr") or item.get("avg_prchs_price") or 0.0, 0.0)
        positions.append({
            "code": code,
            "name": str(item.get("iem_nm") or item.get("prdt_name") or item.get("name") or "").strip(),
            "quantity": quantity,
            "avg_price": avg_price,
        })
    return positions


def normalize_overseas_positions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """해외_주식_조회_잔고의 실제 공식 응답 예시 기반으로 표준화한다."""
    positions: List[Dict[str, Any]] = []
    for item in _normalise_output1(payload):
        code = str(item.get("iem_cd") or item.get("pdno") or item.get("code") or "").strip()
        if not code:
            continue
        quantity = _to_int(item.get("cns_bse_bnc_qty") or item.get("byn_cns_qty") or item.get("hldg_qty") or 0, 0)
        if quantity <= 0:
            continue
        avg_price = _to_float(item.get("fc_phs_uit_pr") or item.get("phs_uit_pr") or item.get("avg_prchs_price") or 0.0, 0.0)
        positions.append({
            "code": code,
            "name": str(item.get("iem_nm") or item.get("prdt_name") or item.get("name") or "").strip(),
            "quantity": quantity,
            "avg_price": avg_price,
        })
    return positions


def build_watchlist_from_positions(positions: Iterable[Dict[str, Any]]) -> List[str]:
    seen = set()
    codes: List[str] = []
    for pos in positions:
        code = str(pos.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def sync_watchlist_from_positions(positions: Iterable[Dict[str, Any]], path: Path = WATCHLIST_PATH) -> List[str]:
    codes = build_watchlist_from_positions(positions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(codes) + ("\n" if codes else ""), encoding="utf-8")
    return codes


def call_nh_rest_api(token: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    response = requests.post(f"{NH_API_BASE}{path}", headers=headers, data=json.dumps(payload, ensure_ascii=False), timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_account_list(token: str, endpoint_url: str | None = None) -> List[str]:
    if not token:
        return []
    url = endpoint_url or ACCOUNT_LIST_PATH
    payload = {}
    try:
        data = call_nh_rest_api(token, url if url.startswith("/") else f"/{url}", payload)
    except Exception:
        return []

    accounts: List[str] = []
    for key in ("Output_0", "output_0", "output", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    act_no = str(item.get("act_no") or item.get("account_no") or "").strip()
                    if act_no:
                        accounts.append(act_no)
            if accounts:
                return accounts
        elif isinstance(value, dict):
            for item in value.values():
                if isinstance(item, list):
                    for entry in item:
                        if isinstance(entry, dict):
                            act_no = str(entry.get("act_no") or entry.get("account_no") or "").strip()
                            if act_no:
                                accounts.append(act_no)
                    if accounts:
                        return accounts
    return accounts


def fetch_domestic_holdings(token: str, account_no: str | None = None, endpoint_url: str | None = None, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    if not account_no and not payload:
        print("미연결: 국내_주식_조회_잔고 계좌 번호가 설정되지 않았습니다.")
        return []

    body = _coerce_payload(payload) or _extract_domestic_account_body(account_no)
    if not body:
        return []
    url = endpoint_url or DOMESTIC_BALANCE_PATH
    payload_json = call_nh_rest_api(token, url if url.startswith("/") else f"/{url}", body)
    return normalize_domestic_positions(payload_json)


def fetch_overseas_holdings(token: str, account_no: str | None = None, endpoint_url: str | None = None, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    if not account_no and not payload:
        print("미연결: 해외_주식_조회_잔고 계좌 번호가 설정되지 않았습니다.")
        return []

    body = _coerce_payload(payload) or _extract_overseas_account_body(account_no)
    if not body:
        return []
    url = endpoint_url or OVERSEAS_BALANCE_PATH
    payload_json = call_nh_rest_api(token, url if url.startswith("/") else f"/{url}", body)
    return normalize_overseas_positions(payload_json)


def fetch_investor_snapshot(code: str, token: str, market_cd: str = "KRX") -> Dict[str, Any]:
    payload = {
        "market_cd": market_cd,
        "iem_cd": code,
        "array_cnt": "1",
    }
    data = call_nh_rest_api(token, DOMESTIC_INVESTOR_PATH, payload)
    return data


def detect_pair_trade_signal(payload: Dict[str, Any]) -> bool:
    """공식 투자자 API 응답에서 외국인 순매수와 기관 합계가 동시에 증가할 때 쌍끌이 매수/매도를 판정한다."""
    raw_output = payload.get("Output_0") if isinstance(payload, dict) else None
    if isinstance(raw_output, list):
        rows = raw_output
    else:
        rows = payload.get("output_0") if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows:
        output = payload.get("output") if isinstance(payload, dict) else {}
        foreign_net = _to_int(output.get("frgn_ntby_qty") or output.get("frgn_net_qty"), 0)
        inst_net = _to_int(output.get("inst_net_qty") or output.get("inst_net") or output.get("institution_net_qty"), 0)
        return foreign_net > 0 and inst_net > 0

    latest = rows[0]
    foreign_net = _to_int(
        latest.get("frgn_ntby_qty")
        or latest.get("frgn_net_qty")
        or latest.get("foreign_net_qty")
        or latest.get("for_rate"),
        0,
    )
    institution_fields = [
        latest.get("gigwan"),
        latest.get("invest"),
        latest.get("account"),
        latest.get("program"),
        latest.get("gigwanz10"),
        latest.get("investz10"),
        latest.get("accountz10"),
        latest.get("programz10"),
    ]
    institution_total = sum(_to_int(v, 0) for v in institution_fields if v is not None)
    return foreign_net > 0 and institution_total > 0


def refresh_watchlist_from_api(token: str, domestic_account_no: str | None = None, overseas_account_no: str | None = None) -> List[str]:
    accounts = fetch_account_list(token)
    domestic_accounts = [domestic_account_no] if domestic_account_no else accounts
    overseas_accounts = [overseas_account_no] if overseas_account_no else accounts

    domestic_positions: List[Dict[str, Any]] = []
    for account in domestic_accounts:
        domestic_positions.extend(fetch_domestic_holdings(token, account_no=account))

    overseas_positions: List[Dict[str, Any]] = []
    for account in overseas_accounts:
        overseas_positions.extend(fetch_overseas_holdings(token, account_no=account))

    positions = domestic_positions + overseas_positions
    return sync_watchlist_from_positions(positions)


def load_watchlist(path: Path = WATCHLIST_PATH) -> List[str]:
    if not path.exists():
        return []
    return [
        x.strip()
        for x in path.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def refresh_watchlist_from_state() -> List[str]:
    old_watchlist = load_watchlist()

    try:
        token_data = get_access_token()
    except Exception as exc:
        print(f"[인증 실패] {type(exc).__name__}: {exc}")
        return old_watchlist

    token = token_data.get("access_token") if isinstance(token_data, dict) else token_data
    if not token:
        print("[인증 실패] access_token 없음")
        return old_watchlist

    domestic_account_no = os.getenv("NH_DOMESTIC_ACCOUNT_NO") or os.getenv("NH_ACCOUNT_NO")
    overseas_account_no = os.getenv("NH_OVERSEAS_ACCOUNT_NO") or os.getenv("NH_ACCOUNT_NO")

    try:
        accounts = fetch_account_list(token)
        domestic_accounts = [domestic_account_no] if domestic_account_no else accounts
        overseas_accounts = [overseas_account_no] if overseas_account_no else accounts
        positions: List[Dict[str, Any]] = []

        for account in domestic_accounts:
            try:
                positions.extend(fetch_domestic_holdings(token, account_no=account))
            except Exception as exc:
                print(
                    f"[국내잔고 조회 실패] {mask_account_no(account)} "
                    f"{type(exc).__name__}: {exc}"
                )

        for account in overseas_accounts:
            try:
                positions.extend(fetch_overseas_holdings(token, account_no=account))
            except Exception as exc:
                print(
                    f"[해외잔고 조회 실패] {mask_account_no(account)} "
                    f"{type(exc).__name__}: {exc}"
                )

        new_codes = build_watchlist_from_positions(positions)
        if not new_codes:
            print(
                "[계좌조회 결과 보유종목 없음 또는 조회 실패] "
                "기존 watchlist를 유지합니다."
            )
            return old_watchlist

        sync_watchlist_from_positions(positions)
        print(f"[계좌 보유종목 동기화] {len(new_codes)}종목")
        return new_codes
    except Exception as exc:
        print(f"[계좌조회 실패] {type(exc).__name__}: {exc}")
        return old_watchlist
