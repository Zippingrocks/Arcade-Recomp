"""ROM-free native checks for the bounded SCSP per-slot mixer word."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPSlotMixerTests(unittest.TestCase):
    def test_envelope_release_word_fields_and_original_byte_write(self):
        native('#include "scsp_slot_mixer.hpp"\n', r'''
using arcaderecomp::scsp::SlotEnvelopeReleaseControl;
int main(){std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned value=0;value<65536u;++value){SlotEnvelopeReleaseControl e;
  const bool ok=e.write16(0x0au,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x7fffu)||e.known_mask(0)!=(ok?0x7fffu:0u))return 1;
  if(e.read16(0x0au,w))return 2;
 }
 for(unsigned value=0;value<256u;++value){SlotEnvelopeReleaseControl e;
  if(e.write8(0x0au,static_cast<std::uint8_t>(value))!=(value<=0x7fu)||
     !e.write8(0x0bu,static_cast<std::uint8_t>(value)))return 3;
 }
 SlotEnvelopeReleaseControl e;
 for(unsigned slot=0;slot<32u;++slot){const unsigned o=slot*0x20u+0x0bu;
  if(!e.write8(o,0xffu)||e.value(slot)!=0xffu||e.known_mask(slot)!=0x00ffu||
     !e.read8(o,b)||b!=0xffu)return 4;
 }
 for(unsigned o:{0x09u,0x0cu,0x3e9u,0x3ecu,0x400u})
  if(e.write8(o,0)||e.write16(o,0)||e.read8(o,b)||e.read16(o,w))return 5;
 e.invalidate();if(e.completed_writes()||e.known_mask(0))return 6;
 return 0;}
''')
        source,report=emit_cpp(words(0x72ff,0x1141,0x000b,0xffff),0)
        self.assertEqual(report.translated,2)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[0]=0x100000u;cpu.a_known[0]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 while(cpu.completed<4u&&step(cpu,bus)){}
 const auto& e=bus.slot_envelope_release_control();
 if(cpu.completed!=2u||e.completed_writes()!=1u||e.value(0)!=0xffu||
    e.known_mask(0)!=0x00ffu)return 1;
 return 0;}
''')

    def test_lfo_word_and_long_clear_into_input_mixer(self):
        native('#include "scsp_slot_mixer.hpp"\n', r'''
using arcaderecomp::scsp::SlotLfoControl;
int main(){SlotLfoControl l;std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned slot=0;slot<32u;++slot){const unsigned o=slot*0x20u+0x12u;
  if(l.read8(o,b)||l.read16(o,w)||!l.read16_discard(o)||
     !l.write16(o,static_cast<std::uint16_t>(slot*0x8421u))||
     !l.read16(o,w)||w!=static_cast<std::uint16_t>(slot*0x8421u))return 1;
 }
 for(unsigned value=0;value<65536u;++value){SlotLfoControl x;
  if(!x.write16(0x12u,static_cast<std::uint16_t>(value))||
     !x.read16(0x12u,w)||w!=value)return 2;
 }
 SlotLfoControl lanes;if(!lanes.write8(0x12u,0x12u)||lanes.read16(0x12u,w)||
   !lanes.write8(0x13u,0x34u)||!lanes.read16(0x12u,w)||w!=0x1234u)return 3;
 for(unsigned o:{0x11u,0x14u,0x3f1u,0x3f4u,0x400u})
  if(l.read8(o,b)||l.read8_discard(o)||l.write8(o,0)||
     l.read16(o,w)||l.read16_discard(o)||l.write16(o,0))return 4;
 if(l.completed_discarded_reads()!=32u||l.completed_writes()!=32u)return 5;
 l.invalidate();if(l.completed_discarded_reads()||l.completed_writes())return 6;
 return 0;}
''')
        source,report=emit_cpp(words(0x42a8,0x0012,0xffff),0)
        self.assertEqual(report.translated,1)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[0]=0x100000u;cpu.a_known[0]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 if(!step(cpu,bus)||cpu.completed!=1u)return 1;
 if(bus.slot_lfo_control().completed_discarded_reads()!=1u||
    bus.slot_lfo_control().completed_writes()!=1u||bus.slot_lfo_control().value(0)!=0u||
    bus.slot_lfo_control().known_mask(0)!=0xffffu)return 2;
 if(bus.slot_input_mixer_control().completed_discarded_reads()!=1u||
    bus.slot_input_mixer_control().completed_writes()!=1u||
    bus.slot_input_mixer_control().known_mask(0)!=0x007fu)return 3;
 return 0;}
''')

    def test_volume_modulation_words_fields_lanes_and_original_clear(self):
        native('#include "scsp_slot_mixer.hpp"\n', r'''
using arcaderecomp::scsp::SlotVolumeModulationControl;
int main(){std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned value=0;value<65536u;++value){SlotVolumeModulationControl m;
  const bool ok=m.write16(0x0cu,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x03ffu)||m.known_mask(0,0)!=(ok?0x03ffu:0u))return 1;
  if(!m.write16(0x0eu,static_cast<std::uint16_t>(value))||
     !m.read16(0x0eu,w)||w!=value)return 2;
 }
 for(unsigned value=0;value<256u;++value){SlotVolumeModulationControl m;
  if(m.write8(0x0cu,static_cast<std::uint8_t>(value))!=(value<=3u))return 3;
  if(!m.write8(0x0du,static_cast<std::uint8_t>(value))||
     !m.write8(0x0eu,static_cast<std::uint8_t>(value))||
     !m.write8(0x0fu,static_cast<std::uint8_t>(value)))return 4;
 }
 SlotVolumeModulationControl m;
 for(unsigned slot=0;slot<32u;++slot){const unsigned base=slot*0x20u+0x0cu;
  if(!m.read16_discard(base)||!m.write16(base,slot)||
     !m.read16_discard(base+2u)||!m.write16(base+2u,static_cast<std::uint16_t>(~slot)))return 5;
  if(m.value(slot,0)!=slot||m.known_mask(slot,0)!=0x03ffu||
     m.value(slot,1)!=static_cast<std::uint16_t>(~slot)||m.known_mask(slot,1)!=0xffffu)return 6;
 }
 if(m.completed_discarded_reads()!=64u||m.completed_writes()!=64u)return 7;
 for(unsigned o:{0x0bu,0x10u,0x3ebu,0x3f0u,0x400u})
  if(m.read8(o,b)||m.read8_discard(o)||m.write8(o,0)||
     m.read16(o,w)||m.read16_discard(o)||m.write16(o,0))return 8;
 m.invalidate();if(m.completed_writes()||m.completed_discarded_reads())return 9;
 return 0;}
''')

        source,report=emit_cpp(words(0x72ff,0x42a8,0x000c,0x1141,0x000d,0xffff),0)
        self.assertEqual(report.translated,3)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[0]=0x100000u;cpu.a_known[0]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 while(cpu.completed<10u&&step(cpu,bus)){}
 const auto& v=bus.slot_volume_modulation_control();
 if(cpu.completed!=3u||v.completed_discarded_reads()!=2u||v.completed_writes()!=3u||
    v.value(0,0)!=0x00ffu||v.known_mask(0,0)!=0x03ffu||
    v.value(0,1)!=0u||v.known_mask(0,1)!=0xffffu)return 1;
 return 0;}
''')

    def test_input_mixer_fields_all_values_slots_and_reserved_bits(self):
        native('#include "scsp_slot_mixer.hpp"\n', r'''
using arcaderecomp::scsp::SlotInputMixerControl;
int main(){std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned value=0;value<256u;++value){SlotInputMixerControl m;
  const bool ok=m.write8(0x15u,static_cast<std::uint8_t>(value));
  if(ok!=(value<=0x7fu)||m.completed_writes()!=(ok?1u:0u)||
     m.known_mask(0)!=(ok?0x007fu:0u)||m.value(0)!=(ok?value:0u))return 1;
  if(m.read8(0x15u,b)||m.read16(0x14u,w))return 2;
 }
 for(unsigned value=0;value<65536u;++value){SlotInputMixerControl m;
  if(m.write16(0x14u,static_cast<std::uint16_t>(value))!=(value<=0x7fu))return 3;
 }
 SlotInputMixerControl m;
 for(unsigned slot=0;slot<32u;++slot){const unsigned base=slot*0x20u+0x14u;
  if(!m.write8(base+1u,static_cast<std::uint8_t>(slot))||
     m.value(slot)!=slot||m.known_mask(slot)!=0x007fu)return 4;
  if(m.write8(base,0)||m.read8(base,b)||m.read16(base,w))return 5;
 }
 for(unsigned o:{0x13u,0x16u,0x3f3u,0x3f6u,0x400u})
  if(m.write8(o,0)||m.write16(o,0)||m.read8(o,b)||m.read16(o,w))return 6;
 m.invalidate();if(m.completed_writes()||m.known_mask(0))return 7;
 return 0;}
''')

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
  bus.write8(0x100015u,0x3fu);
  if(bus.slot_input_mixer_control().value(0)!=0x3fu||
     bus.slot_input_mixer_control().known_mask(0)!=0x7fu)return 6;
  for(unsigned address:{0x100011u,0x100018u,0x1003f1u,0x1003f8u,0x100400u}) {
    try{bus.write8(address,0);return 7;}catch(const BusFault&){}
  }
  try{bus.write16(0x100017u,0);return 8;}catch(const BusFault& e){if(!e.write||e.width!=2u)return 9;}
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

    def test_original_nested_input_mixer_initialization_shape(self):
        # Each of 32 slots receives low-byte values 0,8,...120 at offset +0x15.
        image=words(0x7e1f,0x7c0f,0x4282,0x1142,0x0015,0x5002,
                    0x51ce,0xfff8,0x41e8,0x0020,0x51cf,0xffec,0xffff)
        source,report=emit_cpp(image,0)
        self.assertEqual(report.translated,8)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[0]=0x100000u;cpu.a_known[0]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_slot_mixer_research(true);
 while(cpu.completed<1800u&&step(cpu,bus)){}
 if(cpu.completed!=1665u||cpu.a[0]!=0x100400u||
    bus.slot_input_mixer_control().completed_writes()!=512u)return 1;
 for(unsigned slot=0;slot<32u;++slot)if(bus.slot_input_mixer_control().value(slot)!=120u||
    bus.slot_input_mixer_control().known_mask(slot)!=0x007fu)return 2;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
