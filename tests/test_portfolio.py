import unittest

from portfolio import (
    build_watchlist_from_positions,
    detect_pair_trade_signal,
    normalize_domestic_positions,
    normalize_overseas_positions,
)


class PortfolioSyncTest(unittest.TestCase):
    def test_domestic_positions_are_normalized(self):
        payload = {
            "output": {
                "rslt": {
                    "items": [
                        {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "10", "avg_prchs_price": "70000"},
                        {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": "0", "avg_prchs_price": "100000"},
                    ]
                }
            }
        }
        positions = normalize_domestic_positions(payload)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["code"], "005930")
        self.assertEqual(positions[0]["quantity"], 10)
        self.assertEqual(positions[0]["avg_price"], 70000)

    def test_overseas_positions_are_normalized(self):
        payload = {
            "output": {
                "rslt": {
                    "items": [
                        {"pdno": "AAPL", "prdt_name": "Apple Inc", "hldg_qty": "25", "avg_prchs_price": "200.00"},
                    ]
                }
            }
        }
        positions = normalize_overseas_positions(payload)
        self.assertEqual(positions[0]["code"], "AAPL")
        self.assertEqual(positions[0]["quantity"], 25)
        self.assertEqual(positions[0]["avg_price"], 200.0)

    def test_watchlist_is_merged_from_positions(self):
        positions = [
            {"code": "005930", "quantity": 10, "avg_price": 70000},
            {"code": "AAPL", "quantity": 25, "avg_price": 200.0},
            {"code": "005930", "quantity": 10, "avg_price": 70000},
        ]
        lines = build_watchlist_from_positions(positions)
        self.assertEqual(lines, ["005930", "AAPL"])

    def test_pair_trade_signal_requires_real_fields(self):
        payload = {"output": {"frgn_net_qty": 600, "inst_net_qty": 450}}
        self.assertTrue(detect_pair_trade_signal(payload))
        self.assertFalse(detect_pair_trade_signal({"output": {"frgn_net_qty": 600, "inst_net_qty": -100}}))


if __name__ == "__main__":
    unittest.main()
