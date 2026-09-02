from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

from auth import get_access_token

WATCHLIST_PATH = Path("config/watchlist.txt")


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


def normalize_domestic_positions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """국내_주식_조회_잔고 응답에서 보유종목을 표준 형식으로 변환한다."""
    items = payload.get("output", {}).get("rslt", {}).get("items")
    if items is None:
        items = payload.get("output", {}).get("items", [])

    positions: List[Dict[str, Any]] = []
    for item in items or []:
        code = str(item.get("pdno") or item.get("code") or "").strip()
        if not code:
            continue
        quantity = _to_int(item.get("hldg_qty"), 0)
        if quantity <= 0:
            continue
        avg_price = _to_float(item.get("avg_prchs_price"), 0.0)
        positions.append(
            {
                "code": code,
                "name": str(item.get("prdt_name") or item.get("name") or "").strip(),
                "quantity": quantity,
                "avg_price": avg_price,
            }
        )
    return positions


def normalize_overseas_positions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """해외_주식_조회_잔고 응답에서 실제 보유종목과 수량을 추출한다."""
    items = payload.get("output", {}).get("rslt", {}).get("items")
    if items is None:
        items = payload.get("output", {}).get("items", [])

    positions: List[Dict[str, Any]] = []
    for item in items or []:
        code = str(item.get("pdno") or item.get("code") or "").strip()
        if not code:
            continue
        quantity = _to_int(item.get("hldg_qty"), 0)
        if quantity <= 0:
            continue
        avg_price = _to_float(item.get("avg_prchs_price"), 0.0)
        positions.append(
            {
                "code": code,
                "name": str(item.get("prdt_name") or item.get("name") or "").strip(),
                "quantity": quantity,
                "avg_price": avg_price,
            }
        )
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


def fetch_domestic_holdings(token: str, account_no: str | None = None, endpoint_url: str | None = None, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """국내_주식_조회_잔고용 래퍼. 실제 endpoint URL이 준비된 경우에만 호출한다."""
    if not endpoint_url:
        print("미연결: 국내_주식_조회_잔고 endpoint URL/권한이 아직 설정되지 않았습니다.")
        return []

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = payload or {"account_no": account_no} if account_no else payload or {}
    response = requests.post(endpoint_url, headers=headers, data=json.dumps(body), timeout=20)
    response.raise_for_status()
    return normalize_domestic_positions(response.json())


def fetch_overseas_holdings(token: str, account_no: str | None = None, endpoint_url: str | None = None, payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """해외_주식_조회_잔고용 래퍼. 실제 endpoint URL이 준비된 경우에만 호출한다."""
    if not endpoint_url:
        print("미연결: 해외_주식_조회_잔고 endpoint URL/권한이 아직 설정되지 않았습니다.")
        return []

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = payload or {"account_no": account_no} if account_no else payload or {}
    response = requests.post(endpoint_url, headers=headers, data=json.dumps(body), timeout=20)
    response.raise_for_status()
    return normalize_overseas_positions(response.json())


def detect_pair_trade_signal(payload: Dict[str, Any]) -> bool:
    """국내_주식_시세_투자자에서 외국인/기관 순매수 필드가 합쳐져 쌍끌이 매수/매도를 판정한다."""
    output = payload.get("output") or {}
    foreign_net = _to_int(output.get("frgn_net_qty"), 0)
    inst_net = _to_int(output.get("inst_net_qty"), 0)
    return foreign_net > 0 and inst_net > 0


def refresh_watchlist_from_api(token: str, domestic_endpoint: str | None = None, overseas_endpoint: str | None = None) -> List[str]:
    domestic = fetch_domestic_holdings(token, endpoint_url=domestic_endpoint)
    overseas = fetch_overseas_holdings(token, endpoint_url=overseas_endpoint)
    positions = domestic + overseas
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
    try:
        token = get_access_token().get("access_token")
    except Exception:
        token = ""
    if not token:
        return load_watchlist()
    return refresh_watchlist_from_api(token)
