"""Native MC68000 JMP (An) with explicit, independently proven AOT roots."""
import unittest

from arcaderecomp.m68k import decode, discover
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class M68KIndirectJumpNativeTest(unittest.TestCase):
    def test_decode_all_address_registers_and_stop_static_fallthrough(self):
        for reg in range(8):
            ins = decode(words(0x4ed0 | reg), 0)
            self.assertEqual((ins.mnemonic, ins.operands, ins.size),
                             ("jmp_a", (reg,), 2))
        graph, limited = discover(words(0x4ed0, 0x4e71), 0)
        self.assertEqual([(ins.pc, ins.mnemonic) for ins in graph],
                         [(0, "jmp_a")])
        self.assertFalse(limited)

    def test_explicit_root_is_translated_but_not_invented_as_jump_target(self):
        image = words(0x4ed1, 0x4e71, 0x60fe)
        _, ordinary = emit_cpp(image, 0)
        source, rooted = emit_cpp(image, 0, additional_entries=(4,))
        self.assertEqual((ordinary.discovered, ordinary.translated), (1, 1))
        self.assertEqual((rooted.discovered, rooted.translated), (2, 2))
        self.assertIn("case 0x00000004u", source)
        with self.assertRaises(ValueError):
            emit_cpp(image, 0, additional_entries=(3,))

    def test_native_known_jump_unknown_register_and_untranslated_target(self):
        source, report = emit_cpp(words(0x4ed1, 0x4e71, 0x60fe), 0,
                                  additional_entries=(4,))
        self.assertFalse(report.unsupported)
        native(source, r'''
#include <cstdint>
using namespace arcaderecomp_m68k_generated;
int main() {
  Bus bus;
  CPU known; reset_from_vectors(known,0x2000u,0u); known.a[1]=4u; known.a_known[1]=true;
  if(!step(known,bus)||known.pc!=4u||known.completed!=1u)return 1;
  if(!step(known,bus)||known.pc!=4u||known.completed!=2u)return 2;
  CPU unknown; reset_from_vectors(unknown,0x2000u,0u);
  if(step(unknown,bus)||unknown.stop!=Stop::undefined_state||unknown.pc!=0u||unknown.completed)return 3;
  CPU outside; reset_from_vectors(outside,0x2000u,0u); outside.a[1]=2u; outside.a_known[1]=true;
  if(!step(outside,bus)||outside.pc!=2u||outside.completed!=1u)return 4;
  if(step(outside,bus)||outside.stop!=Stop::untranslated_pc||outside.completed!=1u)return 5;
  return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
