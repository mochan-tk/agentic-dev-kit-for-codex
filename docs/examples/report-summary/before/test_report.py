import unittest

from report import render_report


class ReportTests(unittest.TestCase):
    def test_basic_report(self):
        self.assertEqual("Alice\nBob", render_report(["Alice", "Bob"]))


if __name__ == "__main__":
    unittest.main()
