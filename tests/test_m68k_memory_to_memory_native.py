"""Native non-updating MC68000 memory-to-memory MOVE; no ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move, table


class M68kMemoryToMemoryTests(unittest.TestCase):
    def test_decoder_widths_modes_extensions_order_and_exclusions(self):
        cases = ((2, 1, (), 0), (5, 3, (0xfffe,), -2),
                 (7, 0, (0x8000,), -32768),
                 (7, 1, (0x1234, 0x5678), 0x12345678))
        for size in (1, 2, 4):
            for sm, sr, sext, sd in cases:
                for dm, dr, dext, dd in cases:
                    data = move(size, sm, sr, dm, dr, *(sext + dext))
                    ins = decode(data, 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                        (len(data), "move_memory_to_memory",
                         (size, sm, sr, sd, dm, dr, dd)))
                    for end in range(2, len(data)):
                        with self.assertRaises(ValueError):
                            decode(data[:end], 0)
        for sm, sr, dm, dr in ((3, 0, 2, 0), (4, 0, 2, 0),
                               (6, 0, 2, 0), (2, 0, 3, 0),
                               (2, 0, 4, 0), (2, 0, 6, 0),
                               (7, 2, 2, 0), (2, 0, 7, 2)):
            self.assertEqual(decode(move(1, sm, sr, dm, dr, 0, 0), 0).mnemonic,
                             "unsupported")

    def test_native_values_addresses_order_flags_and_aliases(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for source in range(8):
                for destination in range(8):
                    rows.append((len(image), size, source, destination, len(image) + 6))
                    image += move(size, 5, source, 5, destination,
                                  0xfffe, 0x0002)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Transfers:Bus {
 unsigned reads=0,writes=0,ra[2]{},wa[2]{},wv[2]{},value=0,bytes=0;
 std::uint8_t read8(std::uint32_t a)override{ra[reads++]=a;return static_cast<std::uint8_t>(value);}
 std::uint16_t read16(std::uint32_t a)override{ra[reads++]=a;return static_cast<std::uint16_t>(bytes==4&&reads==1?value>>16u:value);}
 void write8(std::uint32_t a,std::uint8_t v)override{wa[writes]=a;wv[writes++]=v;}
 void write16(std::uint32_t a,std::uint16_t v)override{wa[writes]=a;wv[writes++]=v;}
};
int main(){
 const unsigned samples[]={0u,1u,0x7fu,0x80u,0x7fffu,0x8000u,0x12345678u,0x80000000u,0xffffffffu};
 for(const auto&row:rows)for(unsigned sample:samples)for(unsigned x=0;x<2;++x)for(unsigned kx=0;kx<2;++kx){
  CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);for(unsigned i=0;i<8;++i){cpu.a[i]=0x12000000u+i*0x100u;cpu.a_known[i]=true;}
  cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));cpu.sr_known=static_cast<std::uint16_t>(kx?0xfff0u:0xffe0u);
  const auto before=cpu;Transfers bus;bus.bytes=row[1];bus.value=sample;
  if(!step(cpu,bus)||cpu.pc!=row[4]||cpu.completed!=1)return 1;
  const unsigned mask=row[1]==4?0xffffffffu:(1u<<(row[1]*8u))-1u,value=sample&mask;
  const unsigned source=(before.a[row[2]]-2u)&0xffffffu,destination=(before.a[row[3]]+2u)&0xffffffu;
  if(bus.reads!=(row[1]==4?2u:1u)||bus.writes!=(row[1]==4?2u:1u)||bus.ra[0]!=source||bus.wa[0]!=destination)return 2;
  if(bus.wv[0]!=(row[1]==4?value>>16u:value))return 3;
  if(row[1]==4&&(bus.ra[1]!=((source+2u)&0xffffffu)||bus.wa[1]!=((destination+2u)&0xffffffu)||bus.wv[1]!=(value&0xffffu)))return 4;
  const unsigned sign=1u<<(row[1]*8u-1u),flags=(value&sign?8u:0u)|(value==0?4u:0u);
  if(cpu.sr!=(0x2700u|(x<<4)|flags)||cpu.sr_known!=(kx?0xffffu:0xffefu))return 5;
  if(cpu.a!=before.a||cpu.a_known!=before.a_known||cpu.d!=before.d||cpu.d_known!=before.d_known)return 6;
 }
 return 0;}
''')

    def test_unknown_alignment_and_refusals_preserve_uncommitted_cpu(self):
        sources = []
        for size in (1, 2, 4):
            generated, _ = emit_cpp(move(size, 5, 1, 5, 2, 0xfffe, 2) +
                                    words(0xffff), 0)
            sources.append(generated.replace("arcaderecomp_m68k_generated",
                                             f"transfer_{size}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;using Step=bool(*)(CPU&,Bus&);
Step steps[]={transfer_1::step,transfer_2::step,transfer_4::step};
struct Transfers:Bus{
 unsigned attempts=0,accepted=0,deny=0,address[4]{},width[4]{},write[4]{};
 void hit(unsigned a,unsigned w,bool out){address[attempts]=a;width[attempts]=w;write[attempts]=out;++attempts;if(attempts==deny)throw BusFault(a,out,static_cast<std::uint8_t>(w));++accepted;}
 std::uint8_t read8(std::uint32_t a)override{hit(a,1,false);return 0x80;}
 std::uint16_t read16(std::uint32_t a)override{hit(a,2,false);return 0x1234;}
 void write8(std::uint32_t a,std::uint8_t)override{hit(a,1,true);}
 void write16(std::uint32_t a,std::uint16_t)override{hit(a,2,true);}
};
bool same(const CPU&c,const CPU&b){return c.d==b.d&&c.a==b.a&&c.d_known==b.d_known&&c.a_known==b.a_known&&c.sr==b.sr&&c.sr_known==b.sr_known&&c.pc==b.pc&&c.completed==b.completed;}
CPU initial(){CPU c;reset_from_vectors(c,0x2000,0);c.a[1]=0x01000000u;c.a[2]=0x01001000u;c.a_known[1]=c.a_known[2]=true;c.sr=0x271f;c.sr_known=0xffe0;return c;}
int main(){
 for(unsigned i=0;i<3;++i)for(unsigned reg=1;reg<=2;++reg){auto c=initial();c.a_known[reg]=false;auto b=c;Transfers bus;if(steps[i](c,bus)||c.stop!=Stop::undefined_state||bus.attempts||!same(c,b))return 1;}
 for(unsigned i=0;i<3;++i){const unsigned reads=i==2?2u:1u,cycles=reads*2u;for(unsigned denial=1;denial<=cycles;++denial){auto c=initial();auto b=c;Transfers bus;bus.deny=denial;if(steps[i](c,bus)||c.stop!=Stop::bus_access||!same(c,b)||bus.attempts!=denial||bus.accepted!=denial-1u||c.access_write!=(denial>reads)||c.access_width!=(i==0?1u:2u))return 2;}}
 for(unsigned i=1;i<3;++i){auto c=initial();c.a[1]=3;auto b=c;Transfers bus;if(steps[i](c,bus)||c.stop!=Stop::data_address||bus.attempts||!same(c,b)||c.access_write)return 3;c=initial();c.a[2]=1;b=c;if(steps[i](c,bus)||c.stop!=Stop::data_address||bus.attempts!=(i==2?2u:1u)||!same(c,b)||!c.access_write)return 4;}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
