"""Native MC68000 TST.B/W/L non-updating coverage; no ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def tst(size, mode, reg, *extensions):
    return words(0x4a00 | {1: 0, 2: 0x40, 4: 0x80}[size] |
                 mode << 3 | reg, *extensions)


def table(name, rows):
    return f"static const unsigned {name}[][" + str(len(rows[0])) + "]={" + ",".join(
        "{" + ",".join(f"{value & 0xffffffff}u" for value in row) + "}" for row in rows) + "};\n"


class M68kTestOperandTests(unittest.TestCase):
    def test_decoder_widths_modes_extensions_truncation_and_exclusions(self):
        cases = ((0, 3, (), 0, 2), (2, 4, (), 0, 2),
                 (5, 6, (0xfffe,), -2, 4),
                 (7, 0, (0x8000,), -32768, 4),
                 (7, 1, (0x1234, 0x5678), 0x12345678, 6))
        for size in (1, 2, 4):
            for mode, reg, extensions, displacement, length in cases:
                ins = decode(tst(size, mode, reg, *extensions), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (length, "tst", (size, mode, reg,
                                                  displacement)))
            for mode, reg in ((1, 0), (3, 0), (4, 0), (6, 0),
                              (7, 2), (7, 3), (7, 4)):
                self.assertNotEqual(decode(tst(size, mode, reg), 0).mnemonic,
                                    "tst")
        for image in (tst(2, 5, 0), tst(4, 7, 0), tst(4, 7, 1, 0x1234)):
            with self.assertRaises(ValueError):
                decode(image, 0)
        self.assertEqual(decode(words(0x4ac0), 0).mnemonic, "unsupported")

    def test_native_register_and_memory_values_addresses_flags_and_no_writes(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for mode in (0, 2, 5):
                for reg in range(8):
                    displacement = -2 if mode == 5 else 0
                    length = 4 if mode == 5 else 2
                    rows.append((len(image), size, mode, reg,
                                 displacement, length))
                    image += tst(size, mode, reg,
                                 *((0xfffe,) if mode == 5 else ()))
            rows.append((len(image), size, 7, 0, -2, 4))
            image += tst(size, 7, 0, 0xfffe)
            rows.append((len(image), size, 7, 1, 0x00fffffe, 6))
            image += tst(size, 7, 1, 0x00ff, 0xfffe)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0,addresses[2]{},widths[2]{},value=0,bytes=0;
    std::uint8_t read8(std::uint32_t address)override {
        addresses[count]=address;widths[count++]=1;return static_cast<std::uint8_t>(value);
    }
    std::uint16_t read16(std::uint32_t address)override {
        addresses[count]=address;widths[count++]=2;
        return static_cast<std::uint16_t>(bytes==4&&count==1?value>>16u:value);
    }
    void write8(std::uint32_t,std::uint8_t)override{throw std::runtime_error("write");}
    void write16(std::uint32_t,std::uint16_t)override{throw std::runtime_error("write");}
};
int main() {
    const unsigned values[]={0u,1u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,
                             0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};
    for(const auto& row:rows)for(unsigned input:values)
      for(unsigned x=0;x<2;++x)for(unsigned known_x=0;known_x<2;++known_x) {
        const unsigned mask=row[1]==4?0xffffffffu:(1u<<(row[1]*8u))-1u;
        const unsigned sign=1u<<(row[1]*8u-1u),value=input&mask;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned i=0;i<8;++i){cpu.a[i]=0x12001000u+i*4u;cpu.a_known[i]=true;
          cpu.d[i]=(0xa5a55a5au&~mask)|value;cpu.d_known[i]=mask;}
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xffffu:0xffefu);
        const auto before=cpu;Reads bus;bus.value=value;bus.bytes=row[1];
        if(!step(cpu,bus)||cpu.stop!=Stop::none||cpu.pc!=row[0]+row[5]||cpu.completed!=1)return 1;
        const unsigned expected_reads=row[2]==0?0u:(row[1]==4?2u:1u);
        if(bus.count!=expected_reads)return 2;
        if(row[2]!=0) {
          const unsigned logical=row[2]==7?row[4]:before.a[row[3]]+row[4];
          const unsigned address=logical&0xffffffu;
          if(bus.addresses[0]!=address||bus.widths[0]!=(row[1]==1?1u:2u))return 3;
          if(row[1]==4&&(bus.addresses[1]!=((address+2u)&0xffffffu)||bus.widths[1]!=2u))return 4;
        }
        const unsigned flags=(value&sign?8u:0u)|(value==0?4u:0u);
        if(cpu.sr!=(0x2700u|(x<<4)|flags)||cpu.sr_known!=(known_x?0xffffu:0xffefu))return 5;
        if(cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a!=before.a||
           cpu.a_known!=before.a_known)return 6;
      }
    return 0;
}
''')

    def test_unknown_alignment_and_read_refusals_do_not_commit_flags_or_pc(self):
        images = (tst(1, 0, 3), tst(2, 2, 4),
                  tst(4, 7, 1, 0x00ff, 0xfffe))
        sources = []
        for index, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated",
                                          f"tst_{index}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);Step steps[]={tst_0::step,tst_1::step,tst_2::step};
struct Reads:Bus {
    unsigned attempts=0,accepted=0,deny=0,addresses[2]{},widths[2]{};
    void record(unsigned address,unsigned width){addresses[attempts]=address;widths[attempts]=width;
      ++attempts;if(attempts==deny)throw BusFault(address,false,static_cast<std::uint8_t>(width));++accepted;}
    std::uint8_t read8(std::uint32_t a)override{record(a,1);return 0x80;}
    std::uint16_t read16(std::uint32_t a)override{record(a,2);return 0x1234;}
};
bool unchanged(const CPU& cpu,const CPU& before){return cpu.d==before.d&&cpu.a==before.a&&
  cpu.d_known==before.d_known&&cpu.a_known==before.a_known&&cpu.sr==before.sr&&
  cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&cpu.completed==before.completed;}
CPU initial(){CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x80;cpu.d_known[3]=0xff;
  cpu.a[4]=0x01000000;cpu.a_known[4]=true;cpu.sr=0x271f;cpu.sr_known=0xfff0;return cpu;}
int main(){
    auto cpu=initial();cpu.d_known[3]=0;auto before=cpu;Reads bus;
    if(steps[0](cpu,bus)||cpu.stop!=Stop::undefined_state||bus.attempts||!unchanged(cpu,before))return 1;
    cpu=initial();cpu.a_known[4]=false;before=cpu;
    if(steps[1](cpu,bus)||cpu.stop!=Stop::undefined_state||bus.attempts||!unchanged(cpu,before))return 2;
    for(unsigned index=1;index<3;++index)for(unsigned denial=1;denial<=(index==2?2u:1u);++denial){
      cpu=initial();before=cpu;Reads failing;failing.deny=denial;
      if(steps[index](cpu,failing)||cpu.stop!=Stop::bus_access||!unchanged(cpu,before)||
         failing.attempts!=denial||failing.accepted!=denial-1u||cpu.access_write)return 3;
    }
    cpu=initial();cpu.a[4]=1;before=cpu;Reads aligned;
    if(steps[1](cpu,aligned)||cpu.stop!=Stop::data_address||aligned.attempts||
       !unchanged(cpu,before)||cpu.access_address!=1||cpu.access_width!=2||cpu.access_write)return 4;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
