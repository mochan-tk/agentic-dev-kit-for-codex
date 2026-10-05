import unittest

from report import render_report


class ReportTests(unittest.TestCase):
    def test_basic_report(self):
        self.assertEqual("Alice\nBob", render_report(["Alice", "Bob"]))

    def test_empty_input(self):
        self.assertEqual("", render_report([]))

    def test_trims_names_and_omits_blank_entries(self):
        self.assertEqual("Alice\nBob", render_report(["  Alice ", "", " \t ", "\tBob\t"]))

    def test_keeps_duplicate_names(self):
        self.assertEqual("Alice\nAlice", render_report(["Alice", " Alice "]))

    def test_preserves_order_without_mutating_input(self):
        names = ["  Zoe ", "Ada", "  Bob"]
        original = names.copy()
        self.assertEqual("Zoe\nAda\nBob", render_report(names))
        self.assertEqual(original, names)


if __name__ == "__main__":
    unittest.main()
