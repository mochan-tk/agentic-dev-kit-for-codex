"""The whitespace assertion intentionally fails for the supplied seed."""
import unittest

from report import count_nonblank


class ReportTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(0, count_nonblank([]))

    def test_whitespace_only(self):
        self.assertEqual(0, count_nonblank(["   "]))


if __name__ == "__main__":
    unittest.main()
