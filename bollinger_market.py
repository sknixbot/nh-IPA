from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import os
import re
from typing import Any, Dict, Iterable, List, Sequence
from zoneinfo import ZoneInfo

from bollinger import MarketHistory, SymbolConfig, calculate_snapshot, classify_close_risk
from portfolio import (
    call_nh_rest_api,
    fetch_account_list,
    fetch_domestic_holdings,
    fetch_overseas_holdings,
)


DOMESTIC_DAILY_PATH = "/krstock/quote/v1/currentDaily"
OVERSEAS_PERIOD_PATH = "/gbstock/quote/v1/period"
KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def domestic_session_name(quote_time: datetime) -> str:
    current = quote_time.astimezone(KST).time()
    if time(8, 0) <= current < time(8, 50):
        return "한국 프리마켓(NXT)"
    if time(9, 0) <= current <= time(15, 30):
        return "한국 정규장"
    if time(15, 40) <= current <= time(20, 0):
        return "한국 애프터마켓(KRX/NXT)"
    return "한국 시장"


@dataclass(frozen=True)
class LiveQuote:
    symbol: str
    price: float
    volume: float | None
    session_name: str
    quote_time: datetime
    delayed: bool


def _float(row: Dict[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, "", " "):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return None


def _text(row: Dict[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", " "):
            return str(value).strip()
    return ""


def _rows(payload: Dict[str, Any], keys: Iterable[str]) -> List[Dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _history_from_rows(
    rows: Iterable[Dict[str, Any]],
    date_keys: Sequence[str],
    close_keys: Sequence[str],
    volume_keys: Sequence[str],
    current_date: str,
) -> MarketHistory:
    parsed = []
    for row in rows:
        date = re.sub(r"\D", "", _text(row, date_keys))
        if len(date) == 6:
            date = f"20{date}"
        close = _float(row, close_keys)
        if not date or close is None or close <= 0 or date >= current_date:
            continue
        volume = _float(row, volume_keys) or 0.0
        parsed.append((date, close, volume))
    parsed.sort(key=lambda item: item[0])
    return MarketHistory(
        closes=tuple(item[1] for item in parsed),
        volumes=tuple(item[2] for item in parsed),
    )


def fetch_domestic_history(token: str, symbol: str, count: int = 80) -> MarketHistory:
    payload = call_nh_rest_api(
        token,
        DOMESTIC_DAILY_PATH,
        {
            # 볼린저 기준은 정규장 확정 종가이므로 통합시장(UNT)이 아닌 KRX 일봉을 사용한다.
            "market_cd": "KRX",
            "iem_cd": symbol,
            "array_cnt": str(count).zfill(3),
            "view_main_yn": "Y",
        },
    )
    rows = _rows(payload, ("Output_0", "output_0", "output"))
    return _history_from_rows(
        rows,
        ("date", "bsop_date", "stck_bsop_date", "trd_dd"),
        ("close", "close_prc", "trdprc", "stck_clpr", "main_close"),
        ("volume", "acvol", "acml_vol", "movolume"),
        datetime.now(KST).strftime("%Y%m%d"),
    )


def fetch_overseas_history(token: str, symbol: str, count: int = 80) -> MarketHistory:
    now_et = datetime.now(ET)
    payload = call_nh_rest_api(
        token,
        OVERSEAS_PERIOD_PATH,
        {
            "iem_cd": symbol,
            "end_dt": now_et.strftime("%Y%m%d"),
            "count": str(count).zfill(4),
            "maxavg": "060",
            "gubun": "3",
            "xtick": "0001",
            "today_cls": "0",
            "market_cls": "1",
        },
    )
    rows = _rows(payload, ("Output_1", "output_1", "output1"))
    return _history_from_rows(
        rows,
        ("trade_date", "bsop_date", "date"),
        ("close_prc", "trdprc", "close"),
        ("movolume", "acvol", "volume"),
        now_et.strftime("%Y%m%d"),
    )


def fetch_histories(token: str, configs: Iterable[SymbolConfig]) -> Dict[str, MarketHistory]:
    result: Dict[str, MarketHistory] = {}
    for config in configs:
        try:
            history = (
                fetch_domestic_history(token, config.symbol)
                if config.market == "KR"
                else fetch_overseas_history(token, config.symbol)
            )
            if len(history.closes) < 19:
                print(f"[볼린저 제외] {config.symbol}: 확정 종가 {len(history.closes)}개")
                continue
            result[config.symbol] = history
            print(f"[볼린저 기준값] {config.symbol}: 확정 종가 {len(history.closes)}개")
            if len(history.closes) >= 20:
                confirmed = MarketHistory(history.closes[:-1], history.volumes[:-1])
                latest_volume = history.volumes[-1] if history.volumes else None
                snapshot = calculate_snapshot(confirmed, history.closes[-1], latest_volume)
                risks = ",".join(classify_close_risk(snapshot))
                rsi = "NA" if snapshot.rsi14 is None else f"{snapshot.rsi14:.1f}"
                volume_ratio = (
                    "NA" if snapshot.volume_ratio20 is None else f"{snapshot.volume_ratio20:.2f}"
                )
                print(
                    f"[종가 위험] {config.symbol}: 종가={snapshot.price:.4f} "
                    f"%B={snapshot.percent_b:.3f} RSI={rsi} "
                    f"SMA20={snapshot.sma20_direction} SMA60={snapshot.sma60_direction} "
                    f"거래량비={volume_ratio} 판정={risks}"
                )
        except Exception as exc:
            print(f"[볼린저 기준값 실패] {config.symbol}: {type(exc).__name__}: {exc}")
    return result


def merge_configs_with_positions(
    configs: Iterable[SymbolConfig],
    domestic_positions: Iterable[Dict[str, Any]],
    overseas_positions: Iterable[Dict[str, Any]],
    refresh_markets: set[str] | None = None,
) -> List[SymbolConfig]:
    refresh_markets = refresh_markets or {"KR", "US"}
    merged: Dict[str, SymbolConfig] = {}
    for config in configs:
        groups = tuple(
            group
            for group in config.groups
            if group != "holding" or config.market not in refresh_markets
        )
        if groups:
            merged[config.symbol] = SymbolConfig(
                config.symbol,
                config.name,
                config.market,
                groups,
                config.enabled,
            )

    for market, positions in (("KR", domestic_positions), ("US", overseas_positions)):
        for position in positions:
            symbol = str(position.get("code") or "").strip().upper()
            if not symbol:
                continue
            existing = merged.get(symbol)
            position_name = str(position.get("name") or "").strip()
            groups = set(existing.groups if existing else ())
            groups.add("holding")
            merged[symbol] = SymbolConfig(
                symbol=symbol,
                name=position_name or (existing.name if existing else symbol),
                market=market,
                groups=tuple(group for group in ("holding", "swing", "value") if group in groups),
                enabled=True,
            )
    return list(merged.values())


def refresh_configs_from_holdings(token: str, configs: List[SymbolConfig]) -> List[SymbolConfig]:
    accounts = fetch_account_list(token)
    domestic_account = os.getenv("NH_DOMESTIC_ACCOUNT_NO") or os.getenv("NH_ACCOUNT_NO")
    overseas_account = os.getenv("NH_OVERSEAS_ACCOUNT_NO") or os.getenv("NH_ACCOUNT_NO")
    domestic_accounts = [domestic_account] if domestic_account else accounts
    overseas_accounts = [overseas_account] if overseas_account else accounts
    if not domestic_accounts and not overseas_accounts:
        print("[볼린저 보유그룹] 계좌목록 조회 실패, 고정 목록 유지")
        return configs

    domestic_positions: List[Dict[str, Any]] = []
    overseas_positions: List[Dict[str, Any]] = []
    domestic_success = False
    overseas_success = False
    for account in domestic_accounts:
        try:
            domestic_positions.extend(fetch_domestic_holdings(token, account_no=account))
            domestic_success = True
        except Exception as exc:
            print(f"[볼린저 국내잔고 실패] {type(exc).__name__}")
    for account in overseas_accounts:
        try:
            overseas_positions.extend(fetch_overseas_holdings(token, account_no=account))
            overseas_success = True
        except Exception as exc:
            print(f"[볼린저 해외잔고 실패] {type(exc).__name__}")
    refresh_markets = {
        market
        for market, succeeded in (("KR", domestic_success), ("US", overseas_success))
        if succeeded
    }
    if not refresh_markets:
        print("[볼린저 보유그룹] 잔고 조회 실패, 고정 목록 유지")
        return configs

    refreshed = merge_configs_with_positions(
        configs,
        domestic_positions,
        overseas_positions,
        refresh_markets=refresh_markets,
    )
    print(
        f"[볼린저 보유그룹 갱신] 국내 {len(domestic_positions)} / "
        f"미국 {len(overseas_positions)}"
    )
    return refreshed


def parse_live_quote(message: Dict[str, Any], market: str, delayed: bool) -> LiveQuote | None:
    header = message.get("header") if isinstance(message, dict) else None
    body = message.get("body") if isinstance(message, dict) else None
    if not isinstance(body, dict) or not isinstance(header, dict):
        return None
    if "rsp_cd" in header or "tr_type" in header:
        return None

    if market == "KR":
        symbol = _text(body, ("code", "iem_cd")) or _text(header, ("tr_key",))
        price = _float(body, ("price", "now_pr", "trdprc", "main_close"))
        volume = _float(body, ("volume", "acvol", "acml_vol"))
        session = domestic_session_name(datetime.now(KST))
    else:
        raw_symbol = _text(body, ("symbol", "iem_cd")) or _text(header, ("tr_key",))
        symbol = _text(body, ("ticker",)) or raw_symbol
        price = _float(body, ("trdprc_1z17", "trdprc", "price"))
        volume = _float(body, ("acvol_1z15", "acvol", "volume"))
        period = _text(body, ("marketperiod_clsz1", "marketperiod_cls"))
        session = {
            "1": "미국 프리마켓",
            "2": "미국 정규장",
            "3": "미국 애프터마켓",
        }.get(period, "미국 시장")

    if not symbol or price is None or price <= 0:
        return None
    return LiveQuote(
        symbol=symbol.upper(),
        price=price,
        volume=volume,
        session_name=session,
        quote_time=datetime.now(KST),
        delayed=delayed,
    )
