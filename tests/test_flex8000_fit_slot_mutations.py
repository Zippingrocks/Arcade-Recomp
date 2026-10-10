"""No candidate truth bit can be silently changed in an exact slot match.

The complete artificial fixture is unrelated to the reference's payload.
"""
import unittest
from arcaderecomp.flex8000_fit_slots import ordered_tables, common_slot_permutations
from arcaderecomp.flex8000_fit_constraints import transform
from test_flex8000_fit_slots import report, fit, DEVICE


class SlotMutationTests(unittest.TestCase):
    def test_each_of_128_single_truth_entry_errors_is_rejected(self):
        ordered, _ = ordered_tables(report(), fit(), DEVICE)
        raw = tuple(transform(t, (2, 0, 3, 1), 15, 0) for t in ordered)
        for cell in range(8):
            for bit in range(16):
                with self.subTest(cell=cell, bit=bit):
                    changed = list(raw)
                    changed[cell] ^= 1 << bit
                    result = common_slot_permutations(changed, ordered)
                    self.assertEqual(result['shared_slot_order_count'], 0)


if __name__ == '__main__':
    unittest.main()
