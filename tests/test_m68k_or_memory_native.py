"""Native MC68000 OR.B/W/L non-updating memory,Dn; no ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def or_memory(size, destination, mode, reg, *extensions):
    return words(0x8000 | destination << 9 |
                 {1: 0, 2: 0x40, 4: 0x80}[size] | mode << 3 | reg,
                 *extensions)


def table(name, rows):
    return f"static const unsigned {name}[][" + str(len(rows[0])) + "]={" + ",".join(
        "{" + ",".join(f"{value & 0xffffffff}u" for value in row) + "}" for row in rows) + "};\n"


class M68kOrMemoryTests(unittest.TestCase):
    def test_decoder_widths_registers_modes_extensions_and_exclusions(self):
        cases = ((2, 3, (), 0, 2), (5, 6, (0xfffe,), -2, 4),
                 (7, 0, (0x8000,), -32768, 4),
                 (7, 1, (0x1234, 0x5678), 0x12345678, 6))
        for size in (1, 2, 4):
            for destination in range(8):
                for mode, reg, extensions, displacement, length in cases:
                    ins = decode(or_memory(size, destination, mode, reg,
                                           *extensions), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (length, "or_memory_to_d",
                                      (size, mode, reg, displacement,
                                       destination)))
                for mode, reg in ((0, 0), (1, 0), (3, 0), (4, 0),
                                  (6, 0), (7, 2), (7, 3), (7, 4)):
                    self.assertNotEqual(
                        decode(or_memory(size, destination, mode, reg), 0).mnemonic,
                        "or_memory_to_d")
        for image in (or_memory(2, 0, 5, 0), or_memory(4, 0, 7, 0),
                      or_memory(4, 0, 7, 1, 0x1234)):
            with self.assertRaises(ValueError):
                decode(image, 0)
        self.assertEqual(decode(words(0x80c0), 0).mnemonic, "unsupported")

    def test_native_values_addresses_result_flags_and_long_read_order(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for destination in range(8):
                for mode in (2, 5):
                    for reg in range(8):
                        displacement = -2 if mode == 5 else 0
                        length = 4 if mode == 5 else 2
                        rows.append((len(image), size, destination, mode,
                                     reg, displacement, length))
                        image += or_memory(size, destination, mode, reg,
                                           *((0xfffe,) if mode == 5 else ()))
                rows.append((len(image), size, destination, 7, 0, -2, 4))
                image += or_memory(size, destination, 7, 0, 0xfffe)
                rows.append((len(image), size, destination, 7, 1,
                             0x00fffffe, 6))
                image += or_memory(size, destination, 7, 1, 0x00ff, 0xfffe)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0,addresses[2]{},value=0,bytes=0;
    std::uint8_t read8(std::uint32_t address)override{addresses[count++]=address;return static_cast<std::uint8_t>(value);}
    std::uint16_t read16(std::uint32_t address)override{addresses[count++]=address;
      return static_cast<std::uint16_t>(bytes==4&&count==1?value>>16u:value);}
};
int main(){
 const unsigned values[]={0u,1u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,0xffffu,
                          0x7fffffffu,0x80000000u,0xffffffffu};
 for(const auto& row:rows)for(unsigned destination_value:values)for(unsigned source_value:values)
  for(unsigned x=0;x<2;++x)for(unsigned known_x=0;known_x<2;++known_x){
   const unsigned mask=row[1]==4?0xffffffffu:(1u<<(row[1]*8u))-1u;
   const unsigned sign=1u<<(row[1]*8u-1u),result=(destination_value|source_value)&mask;
   CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
   for(unsigned i=0;i<8;++i){cpu.a[i]=0x12001000u+i*4u;cpu.a_known[i]=true;}
   cpu.d[row[2]]=(0xa5a55a5au&~mask)|(destination_value&mask);cpu.d_known[row[2]]=mask;
   cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
   cpu.sr_known=static_cast<std::uint16_t>(known_x?0xffffu:0xffefu);
   const auto before=cpu;Reads bus;bus.value=source_value&mask;bus.bytes=row[1];
   if(!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1||cpu.stop!=Stop::none)return 1;
   if(cpu.d[row[2]]!=((before.d[row[2]]&~mask)|result)||cpu.d_known[row[2]]!=mask)return 2;
   const unsigned logical=row[3]==7?row[5]:before.a[row[4]]+row[5];
   const unsigned address=logical&0xffffffu;
   if(bus.count!=(row[1]==4?2u:1u)||bus.addresses[0]!=address||
      (row[1]==4&&bus.addresses[1]!=((address+2u)&0xffffffu)))return 3;
   const unsigned flags=(result&sign?8u:0u)|(result==0?4u:0u);
   if(cpu.sr!=(0x2700u|(x<<4)|flags)||cpu.sr_known!=(known_x?0xffffu:0xffefu))return 4;
   if(cpu.a!=before.a||cpu.a_known!=before.a_known)return 5;
 }
 return 0;
}
''')

    def test_unknown_alignment_and_read_refusals_preserve_destination_and_flags(self):
        images = (or_memory(1, 3, 2, 4), or_memory(2, 3, 5, 4, 0xfffe),
                  or_memory(4, 3, 7, 1, 0x00ff, 0xfffe))
        sources = []
        for index, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"or_{index}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);Step steps[]={or_0::step,or_1::step,or_2::step};
struct Reads:Bus{unsigned attempts=0,accepted=0,deny=0,addresses[2]{};
 void record(unsigned a,unsigned w){addresses[attempts++]=a;if(attempts==deny)throw BusFault(a,false,static_cast<std::uint8_t>(w));++accepted;}
 std::uint8_t read8(std::uint32_t a)override{record(a,1);return 0x80;}
 std::uint16_t read16(std::uint32_t a)override{record(a,2);return 0x1234;}};
bool unchanged(const CPU& c,const CPU& b){return c.d==b.d&&c.a==b.a&&c.d_known==b.d_known&&
 c.a_known==b.a_known&&c.sr==b.sr&&c.sr_known==b.sr_known&&c.pc==b.pc&&c.completed==b.completed;}
CPU initial(){CPU c;reset_from_vectors(c,0x2000,0);c.a[4]=0x01000000;c.a_known[4]=true;
 c.d[3]=0x89abcdef;c.d_known[3]=0xffffffff;c.sr=0x271f;c.sr_known=0xfff0;return c;}
int main(){
 for(unsigned i=0;i<3;++i){auto c=initial();c.d_known[3]&=~(i==0?0xffu:i==1?0xffffu:0xffffffffu);
  auto b=c;Reads bus;if(steps[i](c,bus)||c.stop!=Stop::undefined_state||bus.attempts||!unchanged(c,b))return 1;}
 for(unsigned i=0;i<2;++i){auto c=initial();c.a_known[4]=false;auto b=c;Reads bus;
  if(steps[i](c,bus)||c.stop!=Stop::undefined_state||bus.attempts||!unchanged(c,b))return 2;}
 for(unsigned i=0;i<3;++i)for(unsigned denial=1;denial<=(i==2?2u:1u);++denial){
  auto c=initial();auto b=c;Reads bus;bus.deny=denial;if(steps[i](c,bus)||c.stop!=Stop::bus_access||
   !unchanged(c,b)||bus.attempts!=denial||bus.accepted!=denial-1u||c.access_write)return 3;}
 auto c=initial();c.a[4]=3;auto b=c;Reads bus;if(steps[1](c,bus)||c.stop!=Stop::data_address||
  bus.attempts||!unchanged(c,b)||c.access_address!=1||c.access_width!=2||c.access_write)return 4;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
