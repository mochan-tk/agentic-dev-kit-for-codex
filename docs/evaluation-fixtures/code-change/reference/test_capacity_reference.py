"""Public reviewer reference, not a candidate-authored regression result."""
import unittest

from capacity import can_fit


class CapacityReferenceTests(unittest.TestCase):
    def test_exact_capacity(self):
        self.assertIs(True, can_fit(10, 3, 7))

    def test_zero_capacity(self):
        self.assertIs(True, can_fit(0, 0, 0))

    def test_full_capacity_zero_incoming(self):
        self.assertIs(True, can_fit(10, 10, 0))

    def test_empty_to_full(self):
        self.assertIs(True, can_fit(10, 0, 10))

    def test_below_capacity(self):
        self.assertIs(True, can_fit(10, 3, 4))

    def test_over_capacity(self):
        self.assertIs(False, can_fit(10, 8, 3))

    def test_zero_capacity_one_incoming(self):
        self.assertIs(False, can_fit(0, 0, 1))

    def test_nonzero_over_capacity(self):
        self.assertIs(False, can_fit(5, 4, 2))


if __name__ == "__main__":
    unittest.main()
