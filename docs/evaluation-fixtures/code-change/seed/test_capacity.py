"""Two passing baseline tests; the exact-capacity regression is missing."""
import unittest

from capacity import can_fit


class CapacityTests(unittest.TestCase):
    def test_below_capacity(self):
        self.assertIs(True, can_fit(10, 3, 4))

    def test_over_capacity(self):
        self.assertIs(False, can_fit(10, 8, 3))


if __name__ == "__main__":
    unittest.main()
