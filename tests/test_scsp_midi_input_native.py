"""Synthetic-only SCSP MIDI-input FIFO, bus lane and interrupt tests."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPMidiInputTests(unittest.TestCase):
    def test_unknown_empty_full_order_and_ring_wrap(self):
        native('#include "scsp_midi_input.hpp"\n', r'''
using arcaderecomp::scsp::MidiInput;
int main(){
 MidiInput fifo;unsigned count=99;std::uint8_t value=0xa5;
 if(fifo.occupancy(count)||count!=99||fifo.receive(1)||fifo.read(value)||value!=0xa5)return 1;
 fifo.establish_empty_research();
 if(!fifo.occupancy(count)||count||fifo.read(value)||value!=0xa5)return 2;
 // Exercise every byte value, all slots, and repeated nonempty wrap-around.
 for(unsigned i=0;i<4;++i)if(!fifo.receive(static_cast<std::uint8_t>(i)))return 3;
 if(!fifo.occupancy(count)||count!=4||fifo.receive(0xff))return 4;
 for(unsigned i=0;i<256;++i){
  if(!fifo.read(value)||value!=static_cast<std::uint8_t>(i))return 5;
  if(!fifo.occupancy(count)||count!=3||!fifo.receive(static_cast<std::uint8_t>(i+4)))return 6;
 }
 for(unsigned i=0;i<4;++i)if(!fifo.read(value)||value!=i)return 7;
 if(!fifo.occupancy(count)||count||fifo.read(value)||value!=3)return 8;
 if(!fifo.receive(0x80)||!fifo.read(value)||value!=0x80)return 9;
 return 0;
}
''')

    def test_opt_in_bus_widths_do_not_consume_and_discard_does(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u));
 if(bus.establish_midi_input_empty_research()||bus.receive_midi_byte_research(1))return 1;
 for(unsigned phase=0;phase<3;++phase){
  if(phase==1)bus.enable_midi_input_research(true);
  if(phase==2&&!bus.establish_midi_input_empty_research())return 2;
  try{(void)bus.read8(0x100405u);return 3;}catch(const BusFault& e){
   if(e.address!=0x100405u||e.write||e.width!=1u)return 4;
  }
 }
 for(unsigned i=0;i<4;++i)if(!bus.receive_midi_byte_research(static_cast<std::uint8_t>(0xa0+i)))return 5;
 if(bus.receive_midi_byte_research(0xff))return 6;
 for(unsigned a:{0x100404u,0x100406u,0x100407u}){
  try{(void)bus.read8(a);return 7;}catch(const BusFault&){}
 }
 for(unsigned a:{0x100404u,0x100405u}){
  try{(void)bus.read16(a);return 8;}catch(const BusFault& e){if(e.width!=2u)return 9;}
  try{bus.read16_discard(a);return 10;}catch(const BusFault&){}
  try{bus.write8(a,0);return 11;}catch(const BusFault& e){if(!e.write)return 12;}
  try{bus.write16(a,0);return 13;}catch(const BusFault&){}
 }
 unsigned count=0;if(!bus.midi_input().occupancy(count)||count!=4)return 14;
 bus.enable_midi_input_research(false);
 try{(void)bus.read8(0x100405u);return 15;}catch(const BusFault&){}
 if(bus.receive_midi_byte_research(0))return 16;
 bus.enable_midi_input_research(true);
 if(bus.read8(0x1100405u)!=0xa0)return 17;
 bus.read8_discard(0x100405u);
 if(bus.read8(0x100405u)!=0xa2||bus.read8(0x100405u)!=0xa3)return 18;
 try{bus.read8_discard(0x100405u);return 19;}catch(const BusFault&){}
 return 0;
}
''')

    def test_input_irq_asserts_and_releases_both_targets_only(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u));
 bus.enable_midi_input_research(true);
 unsigned level=99;if(bus.interrupt_level(level))return 1; // Controls remain unknown.
 bus.enable_common_control_research(true);
 bus.write16(0x10041eu,0x08);bus.write16(0x10042au,0x08);
 bus.write16(0x100424u,0x08);bus.write16(0x100426u,0x08);bus.write16(0x100428u,0);
 if(bus.interrupt_level(level)||!bus.establish_midi_input_empty_research())return 2;
 if(!bus.interrupt_level(level)||level)return 3;
 // A separate software request must survive every FIFO transition.
 bus.write16(0x100420u,0x20);bus.write16(0x10042cu,0x20);
 const auto& irq=bus.interrupt_control();const auto writes=irq.completed_writes();
 for(unsigned i=0;i<4;++i){
  if(!bus.receive_midi_byte_research(static_cast<std::uint8_t>(i))||
     !irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3)||
     !bus.interrupt_level(level)||level!=3)return 4;
 }
 if(bus.receive_midi_byte_research(4)||irq.pending(0)!=0x28||irq.pending(1)!=0x28)return 5;
 for(unsigned i=0;i<4;++i){
  if(bus.read8(0x100405u)!=i||irq.sound_irq_asserted(3)!=(i<3)||
     irq.main_irq_asserted(3)!=(i<3))return 6;
 }
 if(irq.pending(0)!=0x20||irq.pending(1)!=0x20||irq.pending_known_mask(0)!=0x28||
    irq.pending_known_mask(1)!=0x28||irq.completed_writes()!=writes||
    !bus.interrupt_level(level)||level)return 7;
 if(!bus.receive_midi_byte_research(0x90)||!irq.sound_irq_asserted(3)||
    !irq.main_irq_asserted(3))return 8;
 return 0;
}
''')

    def test_aot_four_reads_use_only_explicit_supplied_bytes(self):
        source, report = emit_cpp(words(0x102d, 0x0405, 0x122d, 0x0405,
                                        0x142d, 0x0405, 0x162d, 0x0405, 0xffff), 0)
        self.assertEqual(report.translated, 4)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){
 for(unsigned supplied=0;supplied<=4;++supplied){
  CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[5]=0x100000;cpu.a_known[5]=true;
  SoundROMBus bus(std::vector<std::uint8_t>(0x80000u));bus.enable_midi_input_research(true);
  if(!bus.establish_midi_input_empty_research())return 1;
  for(unsigned i=0;i<supplied;++i)if(!bus.receive_midi_byte_research(static_cast<std::uint8_t>(0x80+i)))return 2;
  for(unsigned i=0;i<supplied;++i){
   if(!step(cpu,bus)||cpu.d[i]!=(0x80u+i)||cpu.d_known[i]!=0xffu||cpu.completed!=i+1)return 3;
  }
  if(supplied<4){const auto sr=cpu.sr;const auto known=cpu.sr_known;
   if(step(cpu,bus)||cpu.stop!=Stop::bus_access||cpu.access_address!=0x100405u||
      cpu.access_write||cpu.completed!=supplied||cpu.pc!=4*supplied||
      cpu.d_known[supplied]||cpu.sr!=sr||cpu.sr_known!=known)return 4;
  }
 }
 return 0;
}
''')

    def test_nonempty_arrival_does_not_reassert_a_cleared_request(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u));
 bus.enable_common_control_research(true);bus.enable_midi_input_research(true);
 bus.write16(0x10041eu,8);bus.write16(0x10042au,8);
 if(!bus.establish_midi_input_empty_research()||!bus.receive_midi_byte_research(0x90))return 1;
 const auto& irq=bus.interrupt_control();
 if(!irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3))return 2;
 bus.write16(0x100422u,8);
 if(irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3))return 3;
 if(!bus.receive_midi_byte_research(0x40)||irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3))return 4;
 if(bus.read8(0x100405u)!=0x90||irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3))return 5;
 if(bus.read8(0x100405u)!=0x40||irq.sound_irq_asserted(3)||irq.main_irq_asserted(3))return 6;
 if(!bus.receive_midi_byte_research(0x7f)||!irq.sound_irq_asserted(3)||!irq.main_irq_asserted(3))return 7;
 return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
