from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from alerts import emit_alert
from auth import get_access_token
from bollinger import (
    BollingerAlertEngine,
    MarketHistory,
    SymbolConfig,
    calculate_snapshot,
    event_label,
    format_event,
    load_symbol_configs,
)
from bollinger_market import KST, fetch_histories, parse_live_quote, refresh_configs_from_holdings


CONFIG_PATH = Path("config/bollinger_watchlist.json")
DOMESTIC_WS_URL = "wss://api.nhplug.com:7070/websocket"
OVERSEAS_WS_URL = "wss://api.nhplug.com:7080/websocket"
MAX_KEYS_PER_SESSION = 10
ROTATION_SECONDS = 45


class TokenCache:
    def __init__(self) -> None:
        self.value = ""
        self.issued_at = 0.0

    def get(self) -> str:
        if self.value and time.monotonic() - self.issued_at < 23 * 60 * 60:
            return self.value
        response = get_access_token()
        value = response.get("access_token") if isinstance(response, dict) else response
        if not value:
            raise RuntimeError("access token을 가져오지 못했습니다.")
        self.value = str(value)
        self.issued_at = time.monotonic()
        return self.value


class CompanyDedupe:
    FAMILIES = {
        "000660": "SKHYNIX",
        "SKHY": "SKHYNIX",
        "005930": "SAMSUNG_ELECTRONICS",
        "005935": "SAMSUNG_ELECTRONICS",
    }

    def __init__(self, seconds: int = 600) -> None:
        self.seconds = seconds
        self.sent: Dict[tuple[str, str], float] = {}

    def allow(self, symbol: str, kind: str) -> bool:
        family = self.FAMILIES.get(symbol, symbol)
        key = (family, kind)
        now = time.monotonic()
        previous = self.sent.get(key)
        if previous is not None and now - previous < self.seconds:
            return False
        self.sent[key] = now
        return True

    def related_text(self, symbol: str) -> str:
        family = self.FAMILIES.get(symbol)
        if family == "SKHYNIX":
            return "\n동일기업 연동감시: SK하이닉스 000660 · SKHY"
        if family == "SAMSUNG_ELECTRONICS":
            return "\n동일기업 연동감시: 삼성전자 005930 · 삼성전자우 005935"
        return ""

    def family(self, symbol: str) -> str:
        return self.FAMILIES.get(symbol, symbol)


def _chunks(items: List[SymbolConfig], size: int) -> List[List[SymbolConfig]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _resolve_symbol(raw_symbol: str, configs: Dict[str, SymbolConfig]) -> str | None:
    symbol = raw_symbol.upper()
    if symbol in configs:
        return symbol
    matches = [candidate for candidate in configs if symbol.endswith(candidate)]
    if len(matches) == 1:
        return matches[0]
    return None


async def _send_subscriptions(ws, batch: Iterable[SymbolConfig], token: str, tr_cd: str, tr_type: str) -> None:
    for config in batch:
        request = {
            "header": {"token": token, "tr_type": tr_type},
            "body": {"tr_cd": tr_cd, "tr_key": config.symbol},
        }
        await ws.send(json.dumps(request, ensure_ascii=False))
        await asyncio.sleep(0.12)


async def _run_market_stream(
    market: str,
    configs: List[SymbolConfig],
    histories: Dict[str, MarketHistory],
    engine: BollingerAlertEngine,
    token_cache: TokenCache,
    dedupe: CompanyDedupe,
    end_at: float | None,
) -> None:
    if not configs:
        return
    delayed = market == "US" and os.getenv("NH_OVERSEAS_REALTIME", "").lower() not in {"1", "true", "yes"}
    tr_cd = "rc" if delayed else ("RC" if market == "US" else "mc")
    url = OVERSEAS_WS_URL if market == "US" else DOMESTIC_WS_URL
    batches = _chunks(configs, MAX_KEYS_PER_SESSION)
    batch_index = 0
    retries = 0

    while end_at is None or asyncio.get_running_loop().time() < end_at:
        batch = batches[batch_index]
        available = [config for config in batch if config.symbol in histories]
        batch_index = (batch_index + 1) % len(batches)
        if not available:
            await asyncio.sleep(1)
            continue

        try:
            token = token_cache.get()
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                open_timeout=20,
            ) as ws:
                await _send_subscriptions(ws, available, token, tr_cd, "1")
                print(f"[볼린저 구독] {market}/{tr_cd}: {', '.join(c.symbol for c in available)}")
                retries = 0
                rotate_at = None if len(batches) == 1 else asyncio.get_running_loop().time() + ROTATION_SECONDS
                config_map = {config.symbol: config for config in configs}

                while end_at is None or asyncio.get_running_loop().time() < end_at:
                    now = asyncio.get_running_loop().time()
                    if rotate_at is not None and now >= rotate_at:
                        break
                    timeout = 5.0
                    if end_at is not None:
                        timeout = min(timeout, max(0.1, end_at - now))
                    if rotate_at is not None:
                        timeout = min(timeout, max(0.1, rotate_at - now))
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        message = json.loads(raw)
                    except (TypeError, ValueError):
                        continue

                    quote = parse_live_quote(message, market, delayed)
                    if quote is None:
                        continue
                    symbol = _resolve_symbol(quote.symbol, config_map)
                    if symbol is None:
                        continue
                    if symbol != quote.symbol:
                        quote = replace(quote, symbol=symbol)
                    snapshot = calculate_snapshot(histories[symbol], quote.price, quote.volume)
                    session_key = f"{quote.quote_time.astimezone(KST):%Y%m%d}:{quote.session_name}"
                    events = engine.evaluate(symbol, session_key, snapshot)
                    for event in events:
                        if not dedupe.allow(symbol, event.kind):
                            print(f"[동일기업 중복억제] {symbol} {event.kind}")
                            continue
                        message_text = format_event(
                            event,
                            config_map[symbol],
                            quote.session_name,
                            quote.quote_time,
                            quote.delayed,
                        ) + dedupe.related_text(symbol)
                        emit_alert(
                            event_label(event.kind),
                            message_text,
                            dedupe_key=f"{session_key}:{dedupe.family(symbol)}:{event.kind}",
                        )
                        print(f"[볼린저 알림] {symbol} {event.kind} {quote.price}")

                try:
                    await _send_subscriptions(ws, available, token, tr_cd, "2")
                except Exception:
                    pass
        except (ConnectionClosed, ConnectionClosedError, ConnectionResetError, OSError, asyncio.TimeoutError) as exc:
            retries += 1
            wait_seconds = min(2 ** min(retries - 1, 4), 16)
            print(f"[볼린저 재연결] {market}: {type(exc).__name__}; {wait_seconds}초 후")
            await asyncio.sleep(wait_seconds)


async def monitor_bollinger(
    seconds: int = 0,
    config_path: Path = CONFIG_PATH,
    markets: set[str] | None = None,
) -> None:
    configs = load_symbol_configs(config_path)
    token_cache = TokenCache()
    configs = refresh_configs_from_holdings(token_cache.get(), configs)
    selected_markets = {market.upper() for market in (markets or {"KR", "US"})}
    configs = [config for config in configs if config.market in selected_markets]
    if not configs:
        raise RuntimeError("볼린저 감시 종목이 없습니다.")

    histories = fetch_histories(token_cache.get(), configs)
    if not histories:
        raise RuntimeError("볼린저 기준이 될 일봉 데이터를 가져오지 못했습니다.")

    engine = BollingerAlertEngine()
    dedupe = CompanyDedupe()
    loop = asyncio.get_running_loop()
    end_at = loop.time() + seconds if seconds > 0 else None
    domestic = [config for config in configs if config.market == "KR"]
    overseas = [config for config in configs if config.market == "US"]

    print(
        f"[볼린저 시작] 국내 {len(domestic)} / 미국 {len(overseas)} / "
        f"미국채널={'실시간 RC' if os.getenv('NH_OVERSEAS_REALTIME') else '지연 rc'}"
    )
    await asyncio.gather(
        _run_market_stream("KR", domestic, histories, engine, token_cache, dedupe, end_at),
        _run_market_stream("US", overseas, histories, engine, token_cache, dedupe, end_at),
    )
