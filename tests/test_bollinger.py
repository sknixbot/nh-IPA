import json
import tempfile
import unittest
from pathlib import Path

from bollinger import (
    BollingerAlertEngine,
    IndicatorSnapshot,
    MarketHistory,
    SymbolConfig,
    calculate_snapshot,
    classify_close_risk,
    load_symbol_configs,
)
from bollinger_monitor import CompanyDedupe, _resolve_symbol


def snapshot(price: float, lower: float = 90.0, upper: float = 110.0) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        price=price,
        middle=100.0,
        upper=upper,
        lower=lower,
        percent_b=(price - lower) / (upper - lower),
        rsi14=50.0,
        sma20_direction="상승",
        sma60_direction="상승",
        volume_ratio20=1.0,
    )


class BollingerCalculationTest(unittest.TestCase):
    def test_flat_history_has_expected_live_band(self):
        history = MarketHistory(tuple([100.0] * 60), tuple([1000.0] * 60))
        result = calculate_snapshot(history, 100.0, 2000.0)
        self.assertAlmostEqual(result.middle, 100.0)
        self.assertAlmostEqual(result.upper, 100.0)
        self.assertAlmostEqual(result.lower, 100.0)
        self.assertAlmostEqual(result.percent_b, 0.5)
        self.assertAlmostEqual(result.volume_ratio20, 2.0)

    def test_live_price_is_twentieth_daily_value(self):
        history = MarketHistory(tuple(range(1, 20)))
        result = calculate_snapshot(history, 20.0)
        self.assertAlmostEqual(result.middle, 10.5)

    def test_requires_nineteen_confirmed_closes(self):
        with self.assertRaises(ValueError):
            calculate_snapshot(MarketHistory(tuple([100.0] * 18)), 100.0)

    def test_close_risk_combines_band_trend_rsi_and_volume(self):
        result = IndicatorSnapshot(
            price=111.0,
            middle=100.0,
            upper=110.0,
            lower=90.0,
            percent_b=1.05,
            rsi14=75.0,
            sma20_direction="하락",
            sma60_direction="하락",
            volume_ratio20=1.7,
        )
        self.assertEqual(
            classify_close_risk(result),
            ("상단돌파", "20·60일선동반하락", "RSI과열", "거래량급증"),
        )


class BollingerStateTest(unittest.TestCase):
    def test_touch_and_reentry_are_each_sent_once_per_session(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = BollingerAlertEngine(Path(directory) / "state.json")
            self.assertEqual([event.kind for event in engine.evaluate("AMD", "20260914:regular", snapshot(89.0))], ["lower_touch"])
            self.assertEqual(engine.evaluate("AMD", "20260914:regular", snapshot(88.0)), [])
            self.assertEqual(engine.evaluate("AMD", "20260914:regular", snapshot(90.1)), [])
            self.assertEqual([event.kind for event in engine.evaluate("AMD", "20260914:regular", snapshot(90.3))], ["lower_reentry"])
            self.assertEqual(engine.evaluate("AMD", "20260914:regular", snapshot(89.0)), [])

    def test_new_session_resets_alert_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = BollingerAlertEngine(Path(directory) / "state.json")
            engine.evaluate("AMD", "20260914:regular", snapshot(89.0))
            events = engine.evaluate("AMD", "20260915:regular", snapshot(89.0))
            self.assertEqual([event.kind for event in events], ["lower_touch"])


class BollingerConfigTest(unittest.TestCase):
    def test_config_has_unique_symbols_and_all_three_groups(self):
        configs = load_symbol_configs(Path("config/bollinger_watchlist.json"))
        self.assertEqual(len(configs), 24)
        self.assertEqual(len({config.symbol for config in configs}), 24)
        groups = {group for config in configs for group in config.groups}
        self.assertEqual(groups, {"holding", "swing", "value"})

    def test_badges_distinguish_overlap(self):
        self.assertEqual(SymbolConfig("AMD", "AMD", "US", ("holding", "swing", "value")).badge, "⭐")
        self.assertEqual(SymbolConfig("SNDK", "SNDK", "US", ("holding",)).badge, "🔵")
        self.assertEqual(SymbolConfig("VRT", "VRT", "US", ("value",)).badge, "🟢")

    def test_gic_prefixed_symbol_resolves_to_ticker(self):
        configs = {"AAPL": SymbolConfig("AAPL", "Apple", "US", ("value",))}
        self.assertEqual(_resolve_symbol("USAAAPL", configs), "AAPL")

    def test_linked_company_alerts_are_deduplicated(self):
        dedupe = CompanyDedupe(seconds=600)
        self.assertTrue(dedupe.allow("000660", "lower_touch"))
        self.assertFalse(dedupe.allow("SKHY", "lower_touch"))
        self.assertTrue(dedupe.allow("SKHY", "upper_touch"))


if __name__ == "__main__":
    unittest.main()
