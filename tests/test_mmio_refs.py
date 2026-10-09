"""Synthetic checks for static address-reference classification, not ROM data."""
import hashlib
import struct
import unittest
from arcaderecomp.mmio_refs import audit_address

TARGET = 0x00f80000

class AddressReferenceAuditTests(unittest.TestCase):
    def image(self):
        image = bytearray(b'\xff' * 80)
        # Rooted absolute STORE, a terminating unknown word, then an unrooted
        # identical store candidate, LDA, base-relative load, and a raw literal.
        for offset, opcode in [(0, 0x92), (16, 0x92), (32, 0x8c)]:
            struct.pack_into('<2I', image, offset,
                             (opcode << 24) | (6 << 19) | (12 << 10), TARGET)
        struct.pack_into('<2I', image, 48,
                         (0x90 << 24) | (4 << 19) | (16 << 14) | (13 << 10), TARGET)
        struct.pack_into('<I', image, 68, TARGET)
        return bytes(image)

    def test_absolute_displacement_and_literal_are_distinct(self):
        result = audit_address(self.image(), TARGET, (0,))
        self.assertEqual(result['literal_count'], 5)
        self.assertEqual(result['absolute_memory_operand_count'], 2)
        a, b, c, d, e = result['hits']
        self.assertTrue(a['in_selected_graph'])
        self.assertFalse(b['in_selected_graph'])
        self.assertEqual((a['site'], a['access'], a['width_bytes']), ('0x00000000', 'write', 4))
        self.assertEqual(c['classification'], 'absolute_address_construction')
        self.assertEqual(d['classification'], 'memory_displacement_only')
        self.assertEqual(e['classification'], 'literal_only')
        self.assertNotIn('word', a)  # no original opcode bytes in the report

    def test_baseline_hash_guard(self):
        image = self.image()
        result = audit_address(image, TARGET, expected_sha256=hashlib.sha256(image).hexdigest())
        self.assertEqual(result['image_size'], len(image))
        for bad in ['0' * 64, 'invalid']:
            with self.assertRaises(ValueError):
                audit_address(image, TARGET, expected_sha256=bad)

    def test_roots_and_addresses_are_validated(self):
        for roots in [(-4,), (2,), (80,)]:
            with self.assertRaises(ValueError):
                audit_address(self.image(), TARGET, roots)
        for address in [-1, 0x100000000]:
            with self.assertRaises(ValueError):
                audit_address(self.image(), address)

    def test_partial_trailing_word_is_not_read(self):
        result = audit_address(struct.pack('<I', TARGET) + b'\xff\xff', TARGET)
        self.assertEqual(result['literal_count'], 1)
        self.assertEqual(result['hits'][0]['classification'], 'literal_only')

if __name__ == '__main__':
    unittest.main()
