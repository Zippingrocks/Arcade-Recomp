"""No proprietary ROM data; all i960 opwords are synthesized here."""
import struct
import unittest

from arcaderecomp.i960 import DecodeError, decode, discover, read_boot_record, signed


def words(*items):
    return struct.pack("<" + "I" * len(items), *items)


class InstructionDecodingTests(unittest.TestCase):
    def test_sign_extension(self):
        self.assertEqual(signed(0x1ffc, 13), -4)
        self.assertEqual(signed(0xfffff8, 24), -8)
        self.assertEqual(signed(0x1ff8, 13), -8)
        self.assertEqual(signed(8, 24), 8)

    def test_memb_literal_uses_second_instruction_word(self):
        # Our own artificial target, not derived from the game.
        data = words(0x8c803000, 0x10203040, 0x0a000000)
        first = decode(data, 0)
        self.assertEqual(first.mnemonic, "lda")
        self.assertEqual(first.form, "MEMB")
        self.assertEqual(first.size, 8)
        self.assertEqual(first.asm(), "lda 0x10203040, g0")
        self.assertEqual(decode(data, 8).mnemonic, "ret")

    def test_mema_register_relative(self):
        word = (0x8c << 24) | (17 << 19) | (19 << 14) | (1 << 13) | 12
        result = decode(words(word), 0)
        self.assertEqual(result.asm(), "lda 0xc(g3), g1")

    def test_reg_literal_vs_register(self):
        # addo 3, g0, g1
        word = (0x59 << 24) | (17 << 19) | (16 << 14) | (1 << 11) | 3
        ins = decode(words(word), 0)
        self.assertEqual(ins.asm(), "addo 3, g0, g1")
        self.assertEqual(ins.size, 4)

    def test_invalid_register_literal_special_combination(self):
        word = (0x59 << 24) | (17 << 19) | (16 << 14) | (1 << 11) | (1 << 5)
        ins = decode(words(word), 0)
        self.assertFalse(ins.supported)
        self.assertEqual(ins.flow, "unknown")

    def test_branch_target_uses_current_ip(self):
        image = words(0x08fffffc, 0x0a000000)
        branch = decode(image, 0)
        self.assertEqual(branch.mnemonic, "b")
        self.assertEqual(branch.target, 0xfffffffc)
        self.assertEqual(branch.flow, "jump")

    def test_signed_cobr_displacement(self):
        # cmpibne 5, g2, pc-8; is intentionally synthetic.
        word = (0x3d << 24) | (5 << 19) | (18 << 14) | (1 << 13) | 0x1ff8
        result = decode(words(0x0a000000, 0x0a000000, word), 8)
        self.assertEqual(result.mnemonic, "cmpibne")
        self.assertEqual(result.target, 0)
        self.assertEqual(result.operands, ("5", "g2", "0x00000000"))

    def test_ip_relative_memb_is_2_words(self):
        word = (0x8c << 24) | (16 << 19) | (5 << 10)
        ins = decode(words(word, 0xFFFFFFFC), 0)
        self.assertEqual(ins.size, 8)
        self.assertEqual(ins.asm(), "lda 0x00000004, g0")

    def test_unknown_is_explicit(self):
        invalid = decode(words(0xffffffff), 0)
        self.assertFalse(invalid.supported)
        self.assertEqual(invalid.flow, "unknown")

    def test_instruction_alignment_and_truncation(self):
        with self.assertRaises(DecodeError):
            decode(words(0x0a000000), 2)
        with self.assertRaises(DecodeError):
            decode(words(0x8c803000), 0)

    def test_graph_skips_memb_extension_word(self):
        # 0: lda immediate,g0 (8 bytes)
        # 8: addo 3,g0,g1
        # c: unconditional branch to 8
        # 10: ret (unreachable)
        image = words(0x8c803000, 0x10203040,
                      0x598c0803, 0x08fffffc, 0x0a000000)
        graph = discover(image, 0, limit=30)
        self.assertEqual(set(graph["instructions"]), {0, 8, 12})
        self.assertEqual(graph["rejected"], {})
        self.assertIn((12, 8, "jump"), graph["edges"])

    def test_boot_record(self):
        image = words(0, 0xb0, 0, 0x5f0)
        self.assertEqual(read_boot_record(image)["initial_ip"], 0x5f0)


if __name__ == "__main__":
    unittest.main()
