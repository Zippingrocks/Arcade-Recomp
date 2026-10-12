"""Native MC68000 ADDI.B/W/L #imm,Dn coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def addi(size, reg, value, mode=0):
    opcode = 0x0600 | {1: 0, 2: 0x40, 4: 0x80}[size] | mode << 3 | reg
    extensions = ((value >> 16, value & 0xffff) if size == 4 else
                  (value & 0xffff,))
    return words(opcode, *extensions)


class M68kAddImmediateTests(unittest.TestCase):
    def test_decoder_widths_immediates_registers_extensions_and_exclusions(self):
        values = {1: (0, 1, 0x80, 0xff),
                  2: (0, 1, 0x8000, 0xffff),
                  4: (0, 1, 0x80000000, 0xffffffff)}
        for size in (1, 2, 4):
            for reg in range(8):
                for value in values[size]:
                    ins = decode(addi(size, reg, value), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (6 if size == 4 else 4, "addi_d",
                                      (size, reg, value)))
                for mode in range(1, 8):
                    self.assertNotEqual(decode(addi(size, reg, 0, mode), 0).mnemonic,
                                        "addi_d")
        for image in (words(0x0600), words(0x0680, 0x1234)):
            with self.assertRaises(ValueError):
                decode(image, 0)
        self.assertEqual(decode(words(0x06c0), 0).mnemonic, "unsupported")

    def test_native_exhaustive_byte_and_wide_boundaries_against_oracle(self):
        image, rows = bytearray(), []
        immediate_values = {
            1: (0, 1, 0x7f, 0x80, 0xff),
            2: (0, 1, 0x7fff, 0x8000, 0xffff),
            4: (0, 1, 0x7fffffff, 0x80000000, 0xffffffff),
        }
        for size in (1, 2, 4):
            for reg in range(8):
                for immediate in immediate_values[size]:
                    rows.append((len(image), size, reg, immediate,
                                 6 if size == 4 else 4))
                    image += addi(size, reg, immediate)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][5]={" + ",".join(
            "{" + ",".join(f"{value}u" for value in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned boundaries[]={0u,1u,2u,0x7ffeu,0x7fffu,0x8000u,0x8001u,
        0xfffeu,0xffffu,0x7ffffffeu,0x7fffffffu,0x80000000u,0x80000001u,
        0xfffffffeu,0xffffffffu};
    Bus strict;
    for(const auto& row:rows) {
      const unsigned bits=row[1]*8u;
      const unsigned mask=row[1]==4?0xffffffffu:(1u<<bits)-1u;
      const unsigned sign=1u<<(bits-1u), immediate=row[3]&mask;
      const unsigned samples=row[1]==1?256u:sizeof(boundaries)/sizeof(boundaries[0]);
      for(unsigned sample=0;sample<samples;++sample) {
        const unsigned input=(row[1]==1?sample:boundaries[sample])&mask;
        const unsigned result=(input+immediate)&mask;
        const bool carry=std::uint64_t{input}+immediate>mask;
        const bool overflow=(~(input^immediate)&(input^result)&sign)!=0;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.d[row[2]]=(0xa5a55a5au&~mask)|input;cpu.d_known[row[2]]=mask;
        cpu.sr=0x2700u;cpu.sr_known=0xffe0u;const auto before=cpu;
        if(!step(cpu,strict)||cpu.stop!=Stop::none||cpu.pc!=row[0]+row[4]||
           cpu.completed!=1)return 1;
        if(cpu.d[row[2]]!=((before.d[row[2]]&~mask)|result)||
           cpu.d_known[row[2]]!=mask)return 2;
        const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|
                             (result==0?4u:0u)|(overflow?2u:0u);
        if(cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu)return 3;
        for(unsigned reg=0;reg<8;++reg)if(reg!=row[2]&&
          (cpu.d[reg]!=before.d[reg]||cpu.d_known[reg]!=before.d_known[reg]))return 4;
      }
    }
    return 0;
}
''')

    def test_unknown_operand_and_invalid_helper_arguments_fail_atomically(self):
        sources = []
        for size in (1, 2, 4):
            source, _ = emit_cpp(addi(size, 3, 0x89abcdef) + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated",
                                          f"addi_{size}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={addi_1::step,addi_2::step,addi_4::step};
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x01234567u;
    cpu.d_known[3]=0xffffffffu;cpu.sr=0x271fu;cpu.sr_known=0xffe0u;return cpu;
}
int main() {
    Bus strict;const unsigned masks[]={0xffu,0xffffu,0xffffffffu};
    for(unsigned index=0;index<3;++index) {
        auto cpu=initial();cpu.d_known[3]&=~masks[index];const auto before=cpu;
        if(steps[index](cpu,strict)||cpu.stop!=Stop::undefined_state||
           !unchanged(cpu,before))return 1;
    }
    for(unsigned bytes:{0u,3u,5u}) {
        auto cpu=initial();const auto before=cpu;
        if(add_immediate_data(cpu,bytes,3,1,2)||
           cpu.stop!=Stop::unsupported_instruction||!unchanged(cpu,before))return 2;
    }
    auto cpu=initial();const auto before=cpu;
    if(add_immediate_data(cpu,1,8,1,2)||
       cpu.stop!=Stop::unsupported_instruction||!unchanged(cpu,before))return 3;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
