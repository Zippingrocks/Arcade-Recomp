"""ROM-free native checks for SCSP loop/key control and KYONEX."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPSlotKeyTests(unittest.TestCase):
    def test_fields_lanes_reserved_bits_and_write_only_execution(self):
        native('#include "scsp_slot_key.hpp"\n', r'''
using arcaderecomp::scsp::SlotLoopKeyControl;
int main(){std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned value=0;value<65536u;++value){SlotLoopKeyControl k;
  const bool ok=k.write16(0u,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x1fffu)||k.completed_writes()!=(ok?1u:0u)||
     k.completed_executions()!=((ok&&(value&0x1000u))?1u:0u))return 1;
  if(k.read16(0u,w)||k.read8(0u,b))return 2;
 }
 for(unsigned value=0;value<256u;++value){SlotLoopKeyControl k;
  if(k.write8(0u,static_cast<std::uint8_t>(value))!=(value<=0x1fu)||
     !k.write8(1u,static_cast<std::uint8_t>(value)))return 3;
 }
 SlotLoopKeyControl k;
 if(!k.write8(1u,0x5au)||!k.read8(1u,b)||b!=0x5au||k.read8(0u,b)||
    k.value(0)!=0x5au||k.known_mask(0)!=0x00ffu)return 4;
 for(unsigned o:{2u,0x1fu,0x22u,0x3e2u,0x400u})
  if(k.write8(o,0)||k.write16(o,0)||k.read8(o,b)||k.read16(o,w))return 5;
 if(k.write16(1u,0))return 6;
 k.invalidate();if(k.completed_writes()||k.completed_executions()||k.known_mask(0))return 7;
 return 0;}
''')

    def test_execution_applies_all_registered_keys_and_propagates_unknown(self):
        native('#include "scsp_slot_key.hpp"\n', r'''
using arcaderecomp::scsp::SlotLoopKeyControl;
int main(){SlotLoopKeyControl partial;
 if(!partial.write8(5u*0x20u,0x18u)||partial.completed_executions()!=1u)return 1;
 for(unsigned slot=0;slot<32u;++slot){
  if(partial.key_active_known(slot)!=(slot==5u))return 2;
  if(partial.key_active(slot)!=(slot==5u))return 3;
 }
 SlotLoopKeyControl all;
 for(unsigned slot=0;slot<32u;++slot)
  if(!all.write8(slot*0x20u,static_cast<std::uint8_t>((slot&1u)?0x08u:0u)))return 4;
 if(all.completed_executions()!=0u||!all.write8(31u*0x20u,0x18u))return 5;
 for(unsigned slot=0;slot<32u;++slot)
  if(!all.key_active_known(slot)||all.key_active(slot)!=bool(slot&1u))return 6;
 // The authentic all-stop loop proves one more KYONB before each execution;
 // the last command therefore leaves every slot's executed state known off.
 SlotLoopKeyControl stop;
 for(unsigned slot=0;slot<32u;++slot){
  if(!stop.write8(slot*0x20u,0x10u))return 7;
  for(unsigned prior=0;prior<=slot;++prior)
   if(!stop.key_active_known(prior)||stop.key_active(prior))return 8;
  for(unsigned future=slot+1u;future<32u;++future)
   if(stop.key_active_known(future))return 9;
 }
 if(stop.completed_writes()!=32u||stop.completed_executions()!=32u)return 10;
 return 0;}
''')

    def test_bus_and_original_move_byte_shape(self):
        source,report=emit_cpp(words(0x7010,0x1140,0x0000,0xffff),0)
        self.assertEqual(report.translated,2)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[0]=0x100000u;cpu.a_known[0]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 while(cpu.completed<4u&&step(cpu,bus)){}
 const auto& key=bus.slot_loop_key_control();
 if(cpu.completed!=2u||key.completed_writes()!=1u||key.completed_executions()!=1u||
    key.value(0)!=0u||key.known_mask(0)!=0x0f00u)return 1;
 if(!key.key_active_known(0)||key.key_active(0))return 2;
 for(unsigned slot=1;slot<32u;++slot)if(key.key_active_known(slot))return 3;
 try{(void)bus.read8(0x100000u);return 4;}catch(const arcaderecomp::m68k::BusFault&){}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
