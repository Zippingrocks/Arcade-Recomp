"""ROM-free native checks for the bounded SCSP per-slot mixer word."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPSlotMixerTests(unittest.TestCase):
    def test_all_slots_values_lanes_knownness_and_boundaries(self):
        native('#include "scsp_slot_mixer.hpp"\n', r'''
using arcaderecomp::scsp::SlotMixerControl;
int main() {
  SlotMixerControl mixer;std::uint8_t byte=0xa5;std::uint16_t word=0xa55a;
  for(unsigned slot=0;slot<32;++slot) {
    const unsigned base=slot*0x20u+0x16u;
    if(mixer.read8(base,byte)||mixer.read8(base+1u,byte)||mixer.read16(base,word))return 1;
    if(!mixer.read8_discard(base+1u)||!mixer.write8(base+1u,static_cast<std::uint8_t>(slot)))return 2;
    if(mixer.known_mask(slot)!=0x00ffu||mixer.value(slot)!=slot||
       !mixer.read8(base+1u,byte)||byte!=slot||mixer.read8(base,byte)||mixer.read16(base,word))return 3;
    if(!mixer.write8(base,0x80u|slot)||mixer.known_mask(slot)!=0xffffu||
       !mixer.read16(base,word)||word!=((0x80u|slot)<<8u|slot))return 4;
    if(!mixer.write16(base,static_cast<std::uint16_t>(slot*0x8421u))||
       mixer.value(slot)!=static_cast<std::uint16_t>(slot*0x8421u))return 5;
  }
  if(mixer.completed_discarded_reads()!=32u||mixer.completed_writes()!=96u)return 6;
  SlotMixerControl exhaustive;
  for(unsigned value=0;value<65536u;++value) {
    if(!exhaustive.write16(0x16u,static_cast<std::uint16_t>(value))||
       !exhaustive.read16(0x16u,word)||word!=value)return 11;
  }
  if(exhaustive.completed_writes()!=65536u)return 12;
  for(unsigned offset:{0u,0x15u,0x18u,0x3f5u,0x3f8u,0x400u}) {
    if(mixer.read8(offset,byte)||mixer.read8_discard(offset)||mixer.write8(offset,0)||
       mixer.read16(offset,word)||mixer.read16_discard(offset)||mixer.write16(offset,0))return 7;
  }
  if(mixer.read16_discard(0x17u)||mixer.write16(0x17u,0))return 8;
  mixer.invalidate();
  if(mixer.completed_discarded_reads()||mixer.completed_writes())return 9;
  for(unsigned slot=0;slot<32;++slot)if(mixer.value(slot)||mixer.known_mask(slot))return 10;
  return 0;
}
''')

    def test_sound_bus_opt_in_exact_aperture_and_widths(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main() {
  SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
  try{bus.read8_discard(0x100017u);return 1;}catch(const BusFault&){}
  bus.enable_slot_mixer_research(true);
  bus.read8_discard(0x100017u);bus.write8(0x100017u,0x5au);
  if(bus.read8(0x100017u)!=0x5au||bus.slot_mixer_control().known_mask(0)!=0xffu)return 2;
  try{(void)bus.read8(0x100016u);return 3;}catch(const BusFault&){}
  bus.write8(0x100016u,0xa5u);
  if(bus.read16(0x100016u)!=0xa55au)return 4;
  bus.write16(0x1003f6u,0x1234u);
  if(bus.read16(0x1003f6u)!=0x1234u||bus.slot_mixer_control().value(31)!=0x1234u)return 5;
  for(unsigned address:{0x100015u,0x100018u,0x1003f5u,0x1003f8u,0x100400u}) {
    try{bus.write8(address,0);return 6;}catch(const BusFault&){}
  }
  try{bus.write16(0x100017u,0);return 7;}catch(const BusFault& e){if(!e.write||e.width!=2u)return 8;}
  return 0;
}
''')

    def test_original_indexed_clear_shape_crosses_first_18_slots(self):
        # CLR D4; MOVEQ #17,D7; CLR.B ($17,A5,D4.W); ADDI.W #$20,D4; DBF D7,loop.
        image=words(0x4284,0x7e11,0x4235,0x4017,0x0644,0x0020,0x51cf,0xfff6,0xffff)
        source,report=emit_cpp(image,0)
        self.assertEqual(report.translated,5)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){
 CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[5]=0x100000u;cpu.a_known[5]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 while(cpu.completed<200u&&step(cpu,bus)){}
 if(cpu.completed!=56u||cpu.pc!=16u||bus.slot_mixer_control().completed_writes()!=18u||
    bus.slot_mixer_control().completed_discarded_reads()!=18u)return 1;
 for(unsigned slot=0;slot<32;++slot)if(bus.slot_mixer_control().value(slot)!=0u||
    bus.slot_mixer_control().known_mask(slot)!=(slot<18u?0xffu:0u))return 2;
 return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
