"""Bounded tests for original CLR transactions in SCSP's prohibited span."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPProhibitedWindowTests(unittest.TestCase):
    def test_only_discarded_aligned_reads_and_zero_word_writes(self):
        native('#include "scsp_prohibited_window.hpp"\n#include <initializer_list>\n', r'''
using arcaderecomp::scsp::DspProhibitedClearWindow;
int main(){DspProhibitedClearWindow g;
 for(unsigned o=0;o<g.bytes;o+=2u){
  if(!g.read16_discard(o)||!g.write16(o,0u))return 1;
  if(g.write16(o,1u))return 2;
 }
 if(g.completed_discarded_word_reads()!=32u||g.completed_zero_word_writes()!=32u)return 3;
 for(unsigned o:{1u,0x3fu,0x40u,0x42u,0xffffu})
  if(g.read16_discard(o)||g.write16(o,0u))return 4;
 g.invalidate();
 if(g.completed_discarded_word_reads()||g.completed_zero_word_writes())return 5;
 return 0;}
''')

    def test_value_reads_bytes_and_nonzero_writes_remain_strict(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
 bus.enable_dsp_registers_research(true);
 for(unsigned a:{0x1007c0u,0x1007feu}){
  try{(void)bus.read16(a);return 1;}catch(const BusFault&){}
  try{(void)bus.read8(a);return 2;}catch(const BusFault&){}
  try{bus.read8_discard(a);return 3;}catch(const BusFault&){}
  try{bus.write8(a,0);return 4;}catch(const BusFault&){}
  try{bus.write16(a,1);return 5;}catch(const BusFault&){}
  bus.read16_discard(a);bus.write16(a,0);
 }
 if(bus.dsp_prohibited_clear_window().completed_discarded_word_reads()!=2u||
    bus.dsp_prohibited_clear_window().completed_zero_word_writes()!=2u)return 6;
 return 0;}
''')

    def test_original_320_longword_clear_shape_reaches_dsp_buffers(self):
        # MOVE.W #319,D7; CLR.L (A3)+; DBF D7,loop clears exactly the manual's
        # COEF, MADRS, prohibited span, and MPRO address interval.
        source, report = emit_cpp(words(0x3e3c, 0x013f, 0x429b, 0x51cf, 0xfffc, 0xffff), 0)
        self.assertEqual(report.translated, 3)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main(){CPU cpu;reset_from_vectors(cpu,0x2000u,0);cpu.a[3]=0x100700u;cpu.a_known[3]=true;
 SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));bus.enable_dsp_registers_research(true);
 while(cpu.completed<700u&&step(cpu,bus)){}
 if(cpu.completed!=641u||cpu.a[3]!=0x100c00u)return 1;
 if(bus.dsp_coefficients().completed_discarded_reads()!=64u||
    bus.dsp_coefficients().completed_writes()!=64u||
    bus.dsp_memory_addresses().completed_discarded_reads()!=32u||
    bus.dsp_memory_addresses().completed_writes()!=32u||
    bus.dsp_prohibited_clear_window().completed_discarded_word_reads()!=32u||
    bus.dsp_prohibited_clear_window().completed_zero_word_writes()!=32u||
    bus.dsp_microprogram().completed_discarded_reads()!=512u||
    bus.dsp_microprogram().completed_writes()!=512u)return 2;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
