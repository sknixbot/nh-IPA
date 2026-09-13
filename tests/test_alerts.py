import unittest

from alerts import AlertState, _marker_counts, process_foreign_net_buy_alert


class ForeignNetBuyAlertTest(unittest.TestCase):
    def test_emit_once_on_crossing_then_require_reset(self):
        state = AlertState()

        self.assertTrue(process_foreign_net_buy_alert(state, 1200, 300))
        self.assertFalse(process_foreign_net_buy_alert(state, 1250, 1100))
        self.assertFalse(process_foreign_net_buy_alert(state, 400, 1250))
        self.assertTrue(process_foreign_net_buy_alert(state, 1500, 200))

    def test_threshold_and_ratio_both_count_as_significant(self):
        state = AlertState()

        self.assertTrue(process_foreign_net_buy_alert(state, 400, 100, threshold=250, ratio_threshold=1.5))
        self.assertFalse(process_foreign_net_buy_alert(state, 500, 420, threshold=250, ratio_threshold=1.5))


class BollingerRepeatCountTest(unittest.TestCase):
    def test_counts_previous_band_contacts_and_same_hour_duplicate(self):
        items = [
            {"body": "<!-- alert-series:AMD:lower -->"},
            {"body": "<!-- alert-series:AMD:lower -->\n<!-- alert-dedupe:AMD:lower:10 -->"},
            {"body": "<!-- alert-series:NVDA:upper -->"},
        ]
        duplicate, count = _marker_counts(
            items,
            "<!-- alert-dedupe:AMD:lower:10 -->",
            "<!-- alert-series:AMD:lower -->",
        )
        self.assertTrue(duplicate)
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
