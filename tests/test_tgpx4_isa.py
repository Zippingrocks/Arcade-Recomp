"""ROM-free tests for the primary-source MB86235 Type-1 partition."""
import unittest

from arcaderecomp.tgpx4_isa import (
    DecodeError,
    TYPE1_ALU_BITS,
    TYPE1_ALU_SHIFT,
    TYPE1_MUL_BITS,
    TYPE1_MUL_SHIFT,
    TYPE1_TRANSFER_BITS,
    decode_type1,
)


class TGPx4ISATests(unittest.TestCase):
    def test_zero_word_is_documented_type1_partition(self):
        decoded = decode_type1(0)
        self.assertEqual(decoded.raw, 0)
        self.assertEqual(decoded.format_tag, 0)
        self.assertEqual(decoded.alu_field, 0)
        self.assertEqual(decoded.mul_field, 0)
        self.assertEqual(decoded.transfer_field, 0)

    def test_each_field_occupies_exact_documented_bits(self):
        alu = (1 << TYPE1_ALU_BITS) - 1
        mul = (1 << TYPE1_MUL_BITS) - 1
        transfer = (1 << TYPE1_TRANSFER_BITS) - 1
        word = ((alu << TYPE1_ALU_SHIFT) |
                (mul << TYPE1_MUL_SHIFT) | transfer)
        decoded = decode_type1(word)
        self.assertEqual(decoded.alu_field, alu)
        self.assertEqual(decoded.mul_field, mul)
        self.assertEqual(decoded.transfer_field, transfer)

    def test_single_boundary_bits_do_not_bleed_between_fields(self):
        cases = (
            (1 << 60, (1 << 18, 0, 0)),
            (1 << 42, (1, 0, 0)),
            (1 << 41, (0, 1 << 14, 0)),
            (1 << 27, (0, 1, 0)),
            (1 << 26, (0, 0, 1 << 26)),
            (1, (0, 0, 1)),
        )
        for word, fields in cases:
            with self.subTest(bit=word.bit_length() - 1):
                decoded = decode_type1(word)
                self.assertEqual(
                    (decoded.alu_field, decoded.mul_field,
                     decoded.transfer_field), fields)

    def test_all_undocumented_format_tags_fail_closed(self):
        for tag in range(1, 8):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(
                        DecodeError, f"format tag 0b{tag:03b}"):
                    decode_type1(tag << 61)

    def test_refuses_non_integer_and_out_of_range_words(self):
        for word in (-1, 1 << 64, True, None, b"\0" * 8, 1.0):
            with self.subTest(word=word):
                with self.assertRaisesRegex(DecodeError, "unsigned 64-bit"):
                    decode_type1(word)


if __name__ == "__main__":
    unittest.main()
