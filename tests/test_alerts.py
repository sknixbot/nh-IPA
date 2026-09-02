import unittest

from alerts import AlertState, process_foreign_net_buy_alert


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


if __name__ == "__main__":
    unittest.main()
