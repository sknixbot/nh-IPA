from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Dict, Iterable, List, Sequence
from zoneinfo import ZoneInfo


STATE_PATH = Path("data/bollinger_state.json")
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    name: str
    market: str
    groups: tuple[str, ...]
    enabled: bool = True

    @property
    def badge(self) -> str:
        groups = set(self.groups)
        if groups == {"holding", "swing", "value"}:
            return "⭐"
        if {"holding", "swing"}.issubset(groups):
            return "🟣"
        if {"holding", "value"}.issubset(groups):
            return "🟡"
        if groups == {"holding"}:
            return "🔵"
        return "🟢"


@dataclass(frozen=True)
class MarketHistory:
    closes: tuple[float, ...]
    volumes: tuple[float, ...] = ()


@dataclass(frozen=True)
class IndicatorSnapshot:
    price: float
    middle: float
    upper: float
    lower: float
    percent_b: float
    rsi14: float | None
    sma20_direction: str
    sma60_direction: str
    volume_ratio20: float | None


@dataclass(frozen=True)
class BollingerEvent:
    kind: str
    symbol: str
    session_key: str
    snapshot: IndicatorSnapshot


@dataclass
class SymbolState:
    session_key: str = ""
    zone: str = "inside"
    lower_touch_sent: bool = False
    lower_reentry_sent: bool = False
    upper_touch_sent: bool = False
    upper_reentry_sent: bool = False


def load_symbol_configs(path: Path) -> List[SymbolConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    configs: List[SymbolConfig] = []
    for row in raw.get("symbols", []):
        config = SymbolConfig(
            symbol=str(row["symbol"]).strip().upper(),
            name=str(row.get("name") or row["symbol"]).strip(),
            market=str(row["market"]).strip().upper(),
            groups=tuple(str(group).strip().lower() for group in row.get("groups", [])),
            enabled=bool(row.get("enabled", True)),
        )
        if config.enabled:
            configs.append(config)
    return configs


def _sma(values: Sequence[float], length: int) -> float | None:
    if len(values) < length:
        return None
    return fmean(values[-length:])


def _direction(values: Sequence[float], length: int) -> str:
    if len(values) < length + 1:
        return "자료부족"
    current = fmean(values[-length:])
    previous = fmean(values[-length - 1:-1])
    if math.isclose(current, previous, rel_tol=1e-9, abs_tol=1e-9):
        return "횡보"
    return "상승" if current > previous else "하락"


def _rsi(values: Sequence[float], length: int = 14) -> float | None:
    if len(values) < length + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(len(values) - length, len(values))]
    gain = fmean(max(change, 0.0) for change in changes)
    loss = fmean(max(-change, 0.0) for change in changes)
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    rs = gain / loss
    return 100.0 - 100.0 / (1.0 + rs)


def calculate_snapshot(
    history: MarketHistory,
    price: float,
    current_volume: float | None = None,
    length: int = 20,
    multiplier: float = 2.0,
) -> IndicatorSnapshot:
    if price <= 0:
        raise ValueError("price must be positive")
    if len(history.closes) < length - 1:
        raise ValueError(f"at least {length - 1} confirmed closes are required")

    # 일봉 장중 값은 직전 19개 확정 종가 + 현재 체결가를 현재 봉 종가로 사용한다.
    live_closes = list(history.closes) + [float(price)]
    window = live_closes[-length:]
    middle = fmean(window)
    deviation = pstdev(window)
    upper = middle + multiplier * deviation
    lower = middle - multiplier * deviation
    width = upper - lower
    percent_b = (price - lower) / width if width else 0.5

    volume_ratio = None
    if current_volume is not None and len(history.volumes) >= length:
        average_volume = fmean(history.volumes[-length:])
        if average_volume > 0:
            volume_ratio = float(current_volume) / average_volume

    return IndicatorSnapshot(
        price=float(price),
        middle=middle,
        upper=upper,
        lower=lower,
        percent_b=percent_b,
        rsi14=_rsi(live_closes, 14),
        sma20_direction=_direction(live_closes, 20),
        sma60_direction=_direction(live_closes, 60),
        volume_ratio20=volume_ratio,
    )


class BollingerAlertEngine:
    def __init__(self, state_path: Path = STATE_PATH, reentry_margin: float = 0.003):
        self.state_path = state_path
        self.reentry_margin = reentry_margin
        self.states: Dict[str, SymbolState] = self._load_states()

    def _load_states(self) -> Dict[str, SymbolState]:
        if not self.state_path.exists():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return {symbol: SymbolState(**value) for symbol, value in raw.items()}
        except (OSError, ValueError, TypeError):
            return {}

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {symbol: asdict(state) for symbol, state in self.states.items()}
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def evaluate(
        self,
        symbol: str,
        session_key: str,
        snapshot: IndicatorSnapshot,
    ) -> List[BollingerEvent]:
        state = self.states.setdefault(symbol, SymbolState())
        before = asdict(state)
        if state.session_key != session_key:
            state.session_key = session_key
            state.lower_touch_sent = False
            state.lower_reentry_sent = False
            state.upper_touch_sent = False
            state.upper_reentry_sent = False
            state.zone = "inside"

        events: List[BollingerEvent] = []
        price = snapshot.price
        lower_reentry_level = snapshot.lower * (1.0 + self.reentry_margin)
        upper_reentry_level = snapshot.upper * (1.0 - self.reentry_margin)

        if price <= snapshot.lower:
            if state.zone != "below" and not state.lower_touch_sent:
                events.append(BollingerEvent("lower_touch", symbol, session_key, snapshot))
                state.lower_touch_sent = True
            state.zone = "below"
        elif state.zone == "below" and price >= lower_reentry_level:
            if not state.lower_reentry_sent:
                events.append(BollingerEvent("lower_reentry", symbol, session_key, snapshot))
                state.lower_reentry_sent = True
            state.zone = "inside"
        elif price >= snapshot.upper:
            if state.zone != "above" and not state.upper_touch_sent:
                events.append(BollingerEvent("upper_touch", symbol, session_key, snapshot))
                state.upper_touch_sent = True
            state.zone = "above"
        elif state.zone == "above" and price <= upper_reentry_level:
            if not state.upper_reentry_sent:
                events.append(BollingerEvent("upper_reentry", symbol, session_key, snapshot))
                state.upper_reentry_sent = True
            state.zone = "inside"
        elif snapshot.lower < price < snapshot.upper and state.zone not in {"below", "above"}:
            state.zone = "inside"

        if asdict(state) != before:
            self.save()
        return events


def event_label(kind: str) -> str:
    return {
        "lower_touch": "볼린저 하단 터치",
        "lower_reentry": "볼린저 하단 회복",
        "upper_touch": "볼린저 상단 터치",
        "upper_reentry": "볼린저 상단 이탈 실패",
    }.get(kind, kind)


def format_event(
    event: BollingerEvent,
    config: SymbolConfig,
    session_name: str,
    quote_time: datetime,
    delayed: bool,
) -> str:
    snap = event.snapshot
    rsi = "자료부족" if snap.rsi14 is None else f"{snap.rsi14:.1f}"
    volume = "자료부족" if snap.volume_ratio20 is None else f"{snap.volume_ratio20:.2f}배"
    delay_mark = "NH 지연시세" if delayed else "NH 실시간"
    return "\n".join(
        [
            f"{config.badge} {config.name} ({config.symbol})",
            f"신호: {event_label(event.kind)}",
            f"세션: {session_name} · {delay_mark}",
            f"현재가: {snap.price:,.4f}",
            f"상단/중심/하단: {snap.upper:,.4f} / {snap.middle:,.4f} / {snap.lower:,.4f}",
            f"%B: {snap.percent_b:.3f}",
            f"RSI(14): {rsi}",
            f"SMA20/SMA60 방향: {snap.sma20_direction} / {snap.sma60_direction}",
            f"당일 거래량/20일 평균: {volume}",
            f"시세시각(KST): {quote_time.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "판단: 밴드 터치만으로 매수·매도를 확정하지 마십시오.",
        ]
    )


def unique_symbols(configs: Iterable[SymbolConfig]) -> List[str]:
    return list(dict.fromkeys(config.symbol for config in configs if config.enabled))
