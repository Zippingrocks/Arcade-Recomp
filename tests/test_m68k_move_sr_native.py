"""Native MC68000 MOVE immediate to SR supervisor-resident domain."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class M68kMoveSRTests(unittest.TestCase):
    def test_exhaustive_values_privilege_knownness_and_atomic_refusal(self):
        native('#include "m68k_runtime.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){
 for(unsigned value=0;value<65536u;++value){CPU cpu;reset_from_vectors(cpu,0x2000u,0x600100u);
  const bool expected=(value&0x2000u)&&!(value&~0x271fu);
  const bool ok=move_sr(cpu,static_cast<std::uint16_t>(value),0x600104u);
  if(ok!=expected)return 1;
  if(expected){if(cpu.sr!=value||cpu.sr_known!=0xffffu||cpu.pc!=0x600104u||cpu.completed!=1u)return 2;}
  else if(cpu.sr!=0x2700u||cpu.pc!=0x600100u||cpu.completed||cpu.stop!=Stop::unsupported_control)return 3;
 }
 CPU unknown;reset_from_vectors(unknown,0x2000u,0x600100u);unknown.sr_known&=~0x2000u;
 if(move_sr(unknown,0x2200u,0x600104u)||unknown.stop!=Stop::undefined_state)return 4;
 CPU user;reset_from_vectors(user,0x2000u,0x600100u);user.sr&=~0x2000u;
 if(move_sr(user,0x2200u,0x600104u)||user.stop!=Stop::privilege)return 5;
 return 0;}
''')

    def test_authentic_2200_instruction_shape(self):
        source,report=emit_cpp(words(0x46fc,0x2200,0xffff),0)
        self.assertEqual(report.translated,1)
        native(source,r'''
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;Bus bus;reset_from_vectors(cpu,0x2000u,0u);
 if(!step(cpu,bus)||cpu.sr!=0x2200u||cpu.sr_known!=0xffffu||
    cpu.pc!=4u||cpu.completed!=1u)return 1;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
