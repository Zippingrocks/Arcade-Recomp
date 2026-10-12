"""Independent Intel KB Appendix B encodings, not runtime-helper conventions.

Figure B-1 reserves bits 5/6. Table B-1 uses M1/M2 to select FP sources;
indices 16/22 select floating constants, and 4..15/17..21/23..31 are reserved.
"""
import struct
import unittest
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp


def instruction(opcode, src=0, second=0, dst=2, modes=0):
    return ((opcode >> 4) << 24) | ((opcode & 15) << 7) | src | (second << 14) | (dst << 19) | modes


class FloatingOperandEncodingTests(unittest.TestCase):
    def test_reserved_bits_are_rejected_for_every_supported_fp_family(self):
        for opcode in (0x674, 0x677, 0x68a, 0x6c2, 0x6c3, 0x6c9,
                       0x6d9, 0x6e1, 0x6e2, 0x6e3, 0x78b, 0x78c, 0x78d, 0x78f):
            for reserved in (0x20, 0x40, 0x60):
                word = instruction(opcode, modes=0x3000) | reserved
                with self.subTest(opcode=hex(opcode), reserved=reserved):
                    image = struct.pack("<2I", word, 0xffffffff)
                    self.assertEqual(decode(image, 0).mnemonic, "unknown")
                    self.assertIn(0, emit_cpp(image, 0, 8)[1].unsupported)

    def test_real_unary_sources_use_m1_not_reserved_bits(self):
        for opcode in (0x68a, 0x6c2, 0x6c3, 0x6c9, 0x6d9, 0x6e1):
            for source in range(32):
                word = instruction(opcode, src=source, dst=20, modes=0x1800)
                ins = decode(struct.pack("<I", word), 0)
                if source < 4:
                    self.assertEqual(ins.operands, (f"fp{source}", "g4"))
                else:
                    # Explicitly unsupported constants included, not GPR aliases.
                    self.assertEqual(ins.mnemonic, "unknown")

    def test_binary_sources_and_integer_source_exceptions(self):
        for opcode in (0x6e2, 0x6e3, 0x78b, 0x78c, 0x78d, 0x78f):
            for a in range(4):
                for b in range(4):
                    word = instruction(opcode, a, b, 3, 0x3800)
                    self.assertEqual(decode(struct.pack("<I", word), 0).operands,
                                     (f"fp{a}", f"fp{b}", "fp3"))
            for bad in (4, 15, 16, 17, 21, 22, 23, 31):
                for word in (instruction(opcode, bad, 0, 1, 0x3800),
                             instruction(opcode, 0, bad, 1, 0x3800)):
                    self.assertEqual(decode(struct.pack("<I", word), 0).mnemonic,
                                     "unknown")
        for value in range(32):
            cvtir = instruction(0x674, value, 0, 1, 0x3800)
            scaler = instruction(0x677, value, 2, 1, 0x3800)
            self.assertEqual(decode(struct.pack("<I", cvtir), 0).operands,
                             (str(value), "fp1"))
            self.assertEqual(decode(struct.pack("<I", scaler), 0).operands,
                             (str(value), "fp2", "fp1"))


if __name__ == "__main__":
    unittest.main()
