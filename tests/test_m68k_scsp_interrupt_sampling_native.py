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

    def test_execution_allows_masked_and_enters_known_autovector(self):
        source,report=emit_cpp(words(0x4e71,0xffff),0)
        self.assertEqual(report.translated,1)
        native(source,r'''
using namespace arcaderecomp_m68k_generated;
struct IRQBus:Bus{bool known=true;unsigned level=0,writes=0;
 bool interrupt_level(unsigned& v)override{v=level;return known;}
 void write16(std::uint32_t,std::uint16_t)override{++writes;}
 std::uint16_t read16(std::uint32_t a)override{return a&2u?0x0100u:0u;}};
int main(){IRQBus bus;
 for(unsigned mask=0;mask<8u;++mask)for(unsigned level=0;level<8u;++level){
  CPU cpu;reset_from_vectors(cpu,0x2000u,0u);cpu.sr=static_cast<std::uint16_t>(0x2000u|(mask<<8u));
  cpu.sr_known=0xffffu;bus.level=level;bus.writes=0;
  if(!step(cpu,bus))return 1;
  if(level>mask){if(cpu.completed||cpu.pc!=0x100u||cpu.a[7]!=0x1ffau||bus.writes!=3u||
      ((cpu.sr>>8u)&7u)!=level)return 2;}
  else if(cpu.completed!=1u||cpu.pc!=2u||bus.writes)return 3;
 }
 CPU unknown;reset_from_vectors(unknown,0x2000u,0u);unknown.sr=0x2200u;bus.known=false;
 if(step(unknown,bus)||unknown.stop!=Stop::unsupported_control)return 4;
 return 0;}
''')

    def test_autovector_bus_order_frame_and_strict_partial_failure(self):
        source,_=emit_cpp(words(0x4e71,0xffff),0)
        native(source,r'''
using namespace arcaderecomp_m68k_generated;
struct B:Bus{unsigned level=3,op=0,fail=99;std::uint32_t a[5]{};std::uint16_t v[5]{};
 bool interrupt_level(unsigned& x)override{x=level;return true;}
 void write16(std::uint32_t x,std::uint16_t y)override{if(op==fail)throw BusFault(x,true,2);a[op]=x;v[op++]=y;}
 std::uint16_t read16(std::uint32_t x)override{if(op==fail)throw BusFault(x,false,2);a[op]=x;v[op++]=x==0x6cu?0x0060u:0x1234u;return v[op-1];}};
int main(){B b;CPU c;reset_from_vectors(c,0x1000u,0x89abcdeeu);c.sr=0x2215u;c.sr_known=0xffffu;
 if(!step(c,b)||c.completed||c.a[7]!=0xffau||c.pc!=0x00601234u||c.sr!=0x2315u)return 1;
 const std::uint32_t ea[5]={0xffeu,0xffau,0xffcu,0x6cu,0x6eu};
 const std::uint16_t ev[3]={0xcdeeu,0x2215u,0x89abu};
 for(unsigned i=0;i<5u;++i)if(b.a[i]!=ea[i])return 2;
 for(unsigned i=0;i<3u;++i)if(b.v[i]!=ev[i])return 3;
 B f;f.fail=2;CPU d;reset_from_vectors(d,0x1000u,0x200u);d.sr=0x2100u;d.sr_known=0xffffu;
 if(step(d,f)||d.stop!=Stop::bus_access||f.op!=2u||d.a[7]!=0x1000u||d.pc!=0x200u)return 4;
 CPU u;reset_from_vectors(u,0x1000u,0u);u.sr=0x2000u;u.sr_known=0xfff0u;B ub;
 if(step(u,ub)||u.stop!=Stop::undefined_state||ub.op)return 5;
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
