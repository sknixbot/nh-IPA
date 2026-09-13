import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bollinger import SymbolConfig
from bollinger_market import (
    _history_from_rows,
    fetch_domestic_history,
    domestic_session_name,
    merge_configs_with_positions,
    parse_live_quote,
)


class HistoryParserTest(unittest.TestCase):
    def test_rows_are_sorted_and_current_day_is_removed(self):
        rows = [
            {"trade_date": "20260912", "close_prc": "103", "movolume": "30"},
            {"trade_date": "20260910", "close_prc": "101", "movolume": "10"},
            {"trade_date": "20260911", "close_prc": "102", "movolume": "20"},
        ]
        history = _history_from_rows(
            rows,
            ("trade_date",),
            ("close_prc",),
            ("movolume",),
            "20260912",
        )
        self.assertEqual(history.closes, (101.0, 102.0))
        self.assertEqual(history.volumes, (10.0, 20.0))

    def test_domestic_slash_date_is_normalized(self):
        history = _history_from_rows(
            [{"bsop_date": "26/09/11", "stck_clpr": "72000", "acml_vol": "100"}],
            ("bsop_date",),
            ("stck_clpr",),
            ("acml_vol",),
            "20260912",
        )
        self.assertEqual(history.closes, (72000.0,))

    @patch("bollinger_market.call_nh_rest_api")
    def test_domestic_history_count_is_three_digits(self, call_api):
        call_api.return_value = {
            "Output_0": [
                {"bsop_date": "26/09/11", "stck_clpr": "72000", "acml_vol": "100"}
            ]
        }
        fetch_domestic_history("token", "005930", count=80)
        self.assertEqual(call_api.call_args.args[2]["market_cd"], "KRX")
        self.assertEqual(call_api.call_args.args[2]["array_cnt"], "080")


class QuoteParserTest(unittest.TestCase):
    def test_domestic_aftermarket_session_name(self):
        kst = ZoneInfo("Asia/Seoul")
        self.assertEqual(
            domestic_session_name(datetime(2026, 9, 14, 18, 0, tzinfo=kst)),
            "한국 애프터마켓(KRX/NXT)",
        )

    def test_domestic_trade_message(self):
        quote = parse_live_quote(
            {"header": {"tr_cd": "mc", "tr_key": "005930"}, "body": {"price": "81200", "volume": "12345"}},
            "KR",
            False,
        )
        self.assertIsNotNone(quote)
        self.assertEqual(quote.symbol, "005930")
        self.assertEqual(quote.price, 81200.0)

    def test_overseas_delayed_trade_message(self):
        quote = parse_live_quote(
            {
                "header": {"tr_cd": "rc", "tr_key": "USAAAPL"},
                "body": {
                    "gicz15": "USAAAPL",
                    "trdprc_1z17": "315.15",
                    "acvol_1z15": "48128982",
                    "marketperiod_clsz1": "3",
                },
            },
            "US",
            True,
        )
        self.assertIsNotNone(quote)
        self.assertEqual(quote.symbol, "USAAAPL")
        self.assertEqual(quote.session_name, "미국 애프터마켓")
        self.assertTrue(quote.delayed)

    def test_ack_is_not_a_quote(self):
        quote = parse_live_quote(
            {"header": {"tr_type": "1", "rsp_cd": "00000"}, "body": {"tr_key": ["005930"]}},
            "KR",
            False,
        )
        self.assertIsNone(quote)


class HoldingsMergeTest(unittest.TestCase):
    def test_holdings_are_refreshed_without_losing_swing_and_value_groups(self):
        configs = [
            SymbolConfig("AMD", "AMD", "US", ("holding", "swing", "value")),
            SymbolConfig("SNDK", "샌디스크", "US", ("holding",)),
            SymbolConfig("VRT", "버티브", "US", ("value",)),
        ]
        result = merge_configs_with_positions(
            configs,
            [{"code": "005930", "name": "삼성전자"}],
            [{"code": "AMD", "name": "AMD"}, {"code": "AAPL", "name": "Apple"}],
        )
        by_symbol = {config.symbol: config for config in result}
        self.assertNotIn("SNDK", by_symbol)
        self.assertEqual(set(by_symbol["AMD"].groups), {"holding", "swing", "value"})
        self.assertEqual(by_symbol["VRT"].groups, ("value",))
        self.assertEqual(by_symbol["005930"].groups, ("holding",))
        self.assertEqual(by_symbol["AAPL"].groups, ("holding",))


if __name__ == "__main__":
    unittest.main()
