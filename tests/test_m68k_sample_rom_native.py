"""Native Model 2 sound CPU direct and banked sample-ROM address windows."""
import unittest

from test_m68k_bootstrap_native import native


class M68KSampleROMNativeTest(unittest.TestCase):
    def test_exact_region_size_windows_alias_mask_endianness_and_read_only(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
std::uint8_t pattern(unsigned offset){return static_cast<std::uint8_t>((offset>>16u)^offset^0x5au);}
int main(){
 std::vector<std::uint8_t> program(0x80000u,0),samples(0x800000u);
 for(unsigned i=0;i<samples.size();++i)samples[i]=pattern(i);
 SoundROMBus bus(program,samples);
 const unsigned rows[][2]={{0x800000u,0u},{0x9fffffu,0x1fffffu},
  {0xa00000u,0x200000u},{0xdfffffu,0x5fffffu},
  {0xe00000u,0x600000u},{0xffffffu,0x7fffffu}};
 for(const auto& row:rows){if(bus.read8(row[0])!=pattern(row[1]))return 1;
  if(bus.read8(row[0]|0x1000000u)!=pattern(row[1]))return 2;}
 for(const auto& row:rows){const unsigned address=row[0]&~1u,offset=row[1]&~1u;
  const unsigned expected=unsigned(pattern(offset))<<8u|pattern(offset+1u);
  if(bus.read16(address)!=expected)return 3;
  bus.read8_discard(row[0]);bus.read16_discard(address);}
 for(unsigned address:{0x7fffffu,0x680000u}){try{(void)bus.read8(address);return 4;}catch(const BusFault&e){if(e.write||e.width!=1u)return 5;}}
 try{(void)bus.read16(0x9fffffu);return 6;}catch(const BusFault&e){if(e.write||e.width!=2u)return 7;}
 for(unsigned address:{0x800000u,0xa9d9f4u,0xffffffu}){try{bus.write8(address,0);return 8;}catch(const BusFault&e){if(!e.write)return 9;}}
 try{SoundROMBus bad(program,std::vector<std::uint8_t>(0x7fffffu));return 10;}catch(const std::invalid_argument&){}
 SoundROMBus strict(program);try{(void)strict.read8(0x800000u);return 11;}catch(const BusFault&){}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
