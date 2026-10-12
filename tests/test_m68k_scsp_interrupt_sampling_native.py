"""Fail-closed MC68000 sampling of SCSP interrupt-control state."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class M68kSCSPInterruptSamplingTests(unittest.TestCase):
    def test_controller_proves_none_unknown_and_highest_level(self):
        native('#include "scsp_interrupt_control.hpp"\n', r'''
using arcaderecomp::scsp::InterruptControl;
int main(){InterruptControl irq;unsigned level=99;
 if(irq.sound_cpu_interrupt_level(level))return 1;
 if(!irq.write16(0x1eu,0x00c8u)||!irq.write16(0x22u,0x00c8u)||
    !irq.sound_cpu_interrupt_level(level)||level!=0u)return 2;
 irq.observe(6u);if(irq.sound_cpu_interrupt_level(level))return 3;
 if(!irq.write16(0x24u,0x40u)||!irq.write16(0x26u,0x40u)||
    !irq.write16(0x28u,0u)||!irq.sound_cpu_interrupt_level(level)||level!=3u)return 4;
 irq.observe(7u);if(!irq.sound_cpu_interrupt_level(level)||level!=3u)return 5;
 return 0;}
''')

    def test_execution_allows_proven_masked_or_absent_and_refuses_unknown_or_accepted(self):
        source,report=emit_cpp(words(0x4e71,0xffff),0)
        self.assertEqual(report.translated,1)
        native(source,r'''
using namespace arcaderecomp_m68k_generated;
struct IRQBus:Bus{bool known=true;unsigned level=0;bool interrupt_level(unsigned& v)override{v=level;return known;}};
int main(){IRQBus bus;
 for(unsigned mask=0;mask<8u;++mask)for(unsigned level=0;level<8u;++level){
  CPU cpu;reset_from_vectors(cpu,0x2000u,0u);cpu.sr=static_cast<std::uint16_t>(0x2000u|(mask<<8u));bus.level=level;
  const bool ok=step(cpu,bus);if(ok!=(level<=mask))return 1;
  if(!ok&&(cpu.completed||cpu.pc||cpu.stop!=Stop::unsupported_control))return 2;
 }
 CPU unknown;reset_from_vectors(unknown,0x2000u,0u);unknown.sr=0x2200u;bus.known=false;
 if(step(unknown,bus)||unknown.stop!=Stop::unsupported_control)return 3;
 return 0;}
''')

    def test_authentic_scsp_state_proves_no_accepted_request(self):
        source,_=emit_cpp(words(0x46fc,0x2200,0x4e71,0xffff),0)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0u);
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_common_control_research(true);
 bus.write16(0x10041eu,0x00c8u);bus.write16(0x100422u,0x00c8u);
 if(!step(cpu,bus)||!step(cpu,bus)||cpu.completed!=2u||cpu.pc!=6u)return 1;
 bus.interrupt_control();
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
