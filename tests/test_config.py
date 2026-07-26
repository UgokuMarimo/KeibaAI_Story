"""
Tests for src/config.py using standard unittest
"""
import os
import unittest
import src.config as config

class TestConfig(unittest.TestCase):

    def test_config_paths(self):
        """Verify that project paths and DB_PATH are defined correctly."""
        self.assertTrue(os.path.exists(config.PROJECT_ROOT))
        normalized_db_path = os.path.normpath(config.DB_PATH)
        expected_suffix = os.path.normpath(os.path.join('data', 'db', 'predictions.db'))
        self.assertTrue(normalized_db_path.endswith(expected_suffix))
        self.assertTrue(os.path.exists(os.path.dirname(config.DB_PATH)))

    def test_load_best_params_nonexistent(self):
        """Verify that loading non-existent hyperparameter file returns empty dict."""
        res = config.load_best_params_from_file('non_existent_file.txt')
        self.assertIsInstance(res, dict)
        self.assertEqual(res, {})

if __name__ == '__main__':
    unittest.main()
