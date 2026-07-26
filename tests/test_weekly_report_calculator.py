"""
Tests for src/analysis/weekly_report_calculator.py using standard unittest
"""
import unittest
import pandas as pd
from src.analysis.weekly_report_calculator import calculate_performance_for_votes

class TestWeeklyReportCalculator(unittest.TestCase):

    def test_calculate_performance_empty(self):
        """Verify behavior when input DataFrame is empty."""
        df_empty = pd.DataFrame()
        perf, cache = calculate_performance_for_votes(df_empty)
        self.assertEqual(perf['total_amount'], 0)
        self.assertEqual(perf['payout_amount'], 0)
        self.assertEqual(perf['recovery_rate'], 0.0)

if __name__ == '__main__':
    unittest.main()
