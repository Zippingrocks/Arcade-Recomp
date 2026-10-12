"""ROM-free checks for the bounded SCSP DSP COEF register file."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPCoefficientTests(unittest.TestCase):
    def test_all_valid_values_reserved_bits_lanes_and_words(self):
        native('#include "scsp_dsp_coefficients.hpp"\n',r'''
using arcaderecomp::scsp::DspCoefficients;
int main(){std::uint8_t b=0xa5;std::uint16_t w=0xa55a;
 for(unsigned value=0;value<65536u;++value){DspCoefficients c;
  const bool ok=c.write16(0,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x1fffu)||c.completed_writes()!=(ok?1u:0u)||
     c.known_mask(0)!=(ok?0x1fffu:0u)||c.value(0)!=(ok?value:0u))return 1;
  if(c.read16(0,w)||w!=0xa55a)return 2; // reserved high bits remain unknown
 }
 DspCoefficients c;
 for(unsigned i=0;i<64u;++i){const unsigned o=i*2u;
  if(c.read8(o,b)||c.read8(o+1u,b)||c.read16(o,w))return 3;
  if(!c.read16_discard(o)||!c.write16(o,static_cast<std::uint16_t>(i)))return 4;
  if(!c.read8(o+1u,b)||b!=i||c.read8(o,b)||c.known_mask(i)!=0x1fffu)return 5;
 }
 if(c.completed_writes()!=64u||c.completed_discarded_reads()!=64u)return 6;
 for(unsigned value=0;value<256u;++value){DspCoefficients x;
  if(x.write8(0,static_cast<std::uint8_t>(value))!=(value<=0x1fu))return 7;
  if(!x.write8(1,static_cast<std::uint8_t>(value)))return 8;
 }
 for(unsigned o:{0x80u,0x81u,0xffffu})if(c.read8(o,b)||c.read8_discard(o)||
   c.write8(o,0)||c.read16(o,w)||c.read16_discard(o)||c.write16(o,0))return 9;
 if(c.read16_discard(1)||c.write16(1,0))return 10;
 c.invalidate();if(c.completed_writes()||c.completed_discarded_reads())return 11;
 return 0;}
''')

    def test_bus_strict_bounds_and_long_clear_transactions(self):
        # CLR.L (A3)+ repeated 32 times clears exactly 64 COEF words.
        source,report=emit_cpp(words(0x7e1f,0x429b,0x51cf,0xfffc,0xffff),0)
        self.assertEqual(report.translated,3)
        native(source,r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[3]=0x100700u;cpu.a_known[3]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_dsp_registers_research(true);
 while(cpu.completed<200u&&step(cpu,bus)){}
 if(cpu.completed!=65u||cpu.a[3]!=0x100780u||bus.dsp_coefficients().completed_writes()!=64u||
    bus.dsp_coefficients().completed_discarded_reads()!=64u)return 1;
 for(unsigned i=0;i<64u;++i)if(bus.dsp_coefficients().value(i)||
    bus.dsp_coefficients().known_mask(i)!=0x1fffu)return 2;
 bus.read16_discard(0x100780u);
 if(bus.dsp_memory_addresses().completed_discarded_reads()!=1u)return 3;
 try{bus.read16_discard(0x1007c0u);return 4;}catch(const BusFault&){}
 try{bus.write16(0x100700u,0x2000u);return 5;}catch(const BusFault&){}
 if(bus.dsp_coefficients().completed_writes()!=64u)return 6;
 return 0;}
''')

    def test_all_memory_address_words_lanes_and_strict_gap(self):
        native('#include "m68k_sound_bus.hpp"\n',r'''
using namespace arcaderecomp::m68k;
int main(){SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_dsp_registers_research(true);
 for(unsigned i=0;i<32u;++i){const unsigned a=0x100780u+i*2u;
  bus.read16_discard(a);bus.write16(a,static_cast<std::uint16_t>(i*0x8421u));
  if(bus.read16(a)!=static_cast<std::uint16_t>(i*0x8421u))return 1;
 }
 if(bus.dsp_memory_addresses().completed_writes()!=32u||
    bus.dsp_memory_addresses().completed_discarded_reads()!=32u)return 2;
 bus.write8(0x100780u,0x12u);bus.write8(0x100781u,0x34u);
 if(bus.read16(0x100780u)!=0x1234u)return 3;
 for(unsigned a:{0x1007c0u,0x1007deu,0x1007feu}){
  try{bus.read16_discard(a);return 4;}catch(const BusFault&){}
 }
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
