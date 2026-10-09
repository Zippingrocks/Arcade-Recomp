"""ROM-free execution tests for Intel 80960KB leaf branches.

BAL/BALX link without CALL's local register-window transition; BX branches
to an effective address. These test synthetic instruction words only.
"""
import unittest

from arcaderecomp.i960_cpp import emit_cpp
from test_i960_cpp import compile_and_run, words


def memb_indirect(opcode, destination, base):
    """MEMB register-indirect target, with no displacement word."""
    return (opcode << 24) | (destination << 19) | (base << 14) | (4 << 10)


class I960LeafBranchTests(unittest.TestCase):
    def test_bal_uses_g14_and_bx_returns_without_call_frame(self):
        # bal 0x10 ; [unreachable] ; bx (g14)
        branch_back = memb_indirect(0x84, 0, 30)
        data = words(0x0b000010, 0xffffffff, 0xffffffff,
                     0xffffffff, branch_back)
        code, report = emit_cpp(data, 0)
        self.assertEqual(report.discovered, 2)
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, ())
        compile_and_run(code, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    // BAL/BX have no dependency on frame_init() or stack-backed spilling.
    if (!step(cpu, bus) || cpu.ip != 16u || cpu.r[30] != 4u) return 1;
    if (cpu.frame_depth != 0u || cpu.frame_initialized) return 2;
    if (!step(cpu, bus) || cpu.ip != 4u) return 3;
    if (cpu.r[30] != 4u || cpu.frame_depth != 0u) return 4;
    return 0;
}
""")

    def test_balx_resolves_target_before_overwriting_link_register(self):
        # balx (g2),g2 ; ... ; bx (g2)
        branch_link = memb_indirect(0x85, 18, 18)
        branch_back = memb_indirect(0x84, 0, 18)
        data = words(branch_link, 0xffffffff, 0xffffffff,
                     0xffffffff, branch_back)
        code, report = emit_cpp(data, 0, additional_entries=(16,))
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, ())
        compile_and_run(code, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0; cpu.r[18] = 0x11u;
    // Original target = 0x11 (masked to 0x10). Link overwrites g2 with 4.
    if (!step(cpu, bus) || cpu.ip != 16u || cpu.r[18] != 4u) return 1;
    if (!step(cpu, bus) || cpu.ip != 4u) return 2;
    if (cpu.frame_initialized || cpu.frame_depth != 0u) return 3;
    return 0;
}
""")

    def test_eight_byte_balx_links_to_full_next_instruction(self):
        # balx absolute 0x14,g4 is 8 bytes (MEMB displacement word).
        # Its link must be pc+8, not pc+4.
        branch_link = (0x85 << 24) | (20 << 19) | (12 << 10)
        branch_back = memb_indirect(0x84, 0, 20)
        data = words(branch_link, 0x14, 0xffffffff, 0xffffffff,
                     0xffffffff, branch_back)
        code, report = emit_cpp(data, 0, additional_entries=(20,))
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, ())
        compile_and_run(code, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    if (!step(cpu, bus) || cpu.ip != 20u || cpu.r[20] != 8u) return 1;
    if (!step(cpu, bus) || cpu.ip != 8u) return 2;
    if (cpu.frame_depth != 0u) return 3;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
