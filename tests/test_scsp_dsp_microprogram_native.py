"""ROM-free checks for the bounded SCSP DSP MPRO register file."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPMicroprogramTests(unittest.TestCase):
    def test_every_word_byte_lane_knownness_and_bounds(self):
        native('#include "scsp_dsp_coefficients.hpp"\n', r'''
using arcaderecomp::scsp::DspMicroprogram;
int main(){DspMicroprogram m;std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned i=0;i<m.words;++i){const unsigned o=i*2u;
  if(m.read8(o,b)||m.read8(o+1u,b)||m.read16(o,w))return 1;
  if(!m.read16_discard(o)||!m.write16(o,static_cast<std::uint16_t>(i*0x8421u)))return 2;
  if(!m.read16(o,w)||w!=static_cast<std::uint16_t>(i*0x8421u)||
     m.known_mask(i)!=0xffffu)return 3;
 }
 if(m.completed_writes()!=m.words||m.completed_discarded_reads()!=m.words)return 4;
 DspMicroprogram lanes;
 for(unsigned i=0;i<lanes.words;++i){const unsigned o=i*2u;
  if(!lanes.write8(o,static_cast<std::uint8_t>(i))||lanes.read16(o,w)||
     !lanes.read8(o,b)||b!=static_cast<std::uint8_t>(i)||lanes.read8(o+1u,b))return 5;
  if(!lanes.write8(o+1u,static_cast<std::uint8_t>(~i))||!lanes.read16(o,w)||
     w!=static_cast<std::uint16_t>((i&0xffu)<<8|(~i&0xffu)))return 6;
 }
 for(unsigned o:{0x400u,0x401u,0xffffu})if(m.read8(o,b)||m.read8_discard(o)||
    m.write8(o,0)||m.read16(o,w)||m.read16_discard(o)||m.write16(o,0))return 7;
 if(m.read16(1,w)||m.read16_discard(1)||m.write16(1,0))return 8;
 m.invalidate();if(m.completed_writes()||m.completed_discarded_reads()||m.known_mask(0))return 9;
 return 0;}
''')

    def test_bus_exact_aperture_and_reserved_gap(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
 bus.enable_dsp_registers_research(true);
 bus.read16_discard(0x100800u);bus.write16(0x100800u,0x1234u);
 bus.write8(0x100bfeu,0xa5u);bus.write8(0x100bffu,0x5au);
 if(bus.read16(0x100800u)!=0x1234u||bus.read16(0x100bfeu)!=0xa55au||
    bus.dsp_microprogram().completed_discarded_reads()!=1u||
    bus.dsp_microprogram().completed_writes()!=3u)return 1;
 for(unsigned a:{0x1007c0u,0x1007feu}){
  try{(void)bus.read16(a);return 2;}catch(const BusFault&){}
  try{bus.write16(a,1);return 3;}catch(const BusFault&){}
 }
 try{bus.read16_discard(0x100c00u);return 4;}catch(const BusFault&){}
 try{bus.write16(0x100c00u,0);return 5;}catch(const BusFault&){}
 return 0;}
''')

    def test_original_clear_shape_covers_all_512_words(self):
        # MOVE.W #255,D7; CLR.L (A3)+; DBF D7,loop -- the MPRO portion of
        # the original 320-longword clear, isolated from the unknown gap.
        source, report = emit_cpp(words(0x3e3c, 0x00ff, 0x429b, 0x51cf, 0xfffc, 0xffff), 0)
        self.assertEqual(report.translated, 3)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[3]=0x100800u;cpu.a_known[3]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_dsp_registers_research(true);
 while(cpu.completed<600u&&step(cpu,bus)){}
 if(cpu.completed!=513u||cpu.a[3]!=0x100c00u||
    bus.dsp_microprogram().completed_writes()!=512u||
    bus.dsp_microprogram().completed_discarded_reads()!=512u)return 1;
 for(unsigned i=0;i<512u;++i)if(bus.dsp_microprogram().value(i)||
    bus.dsp_microprogram().known_mask(i)!=0xffffu)return 2;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
