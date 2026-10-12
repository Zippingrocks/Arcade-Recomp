"""Native MC68000 NEGX.B/W/L Dn coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def negx(size, reg, mode=0):
    return words(0x4000 | {1: 0, 2: 0x40, 4: 0x80}[size] |
                 mode << 3 | reg)


class M68kNegateExtendTests(unittest.TestCase):
    def test_decoder_all_widths_registers_and_subset_boundaries(self):
        for size in (1, 2, 4):
            for reg in range(8):
                ins = decode(negx(size, reg), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (2, "negx_d", (size, reg)))
                for mode in range(1, 8):
                    self.assertNotEqual(decode(negx(size, reg, mode), 0).mnemonic,
                                        "negx_d")
        for reg in range(8):
            self.assertEqual(decode(words(0x40c0 | reg), 0).mnemonic,
                             "unsupported")

    def test_native_exhaustive_byte_and_wide_boundaries_with_cumulative_zero(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for reg in range(8):
                rows.append((len(image), size, reg))
                image += negx(size, reg)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][3]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned boundaries[]={0u,1u,2u,0x7fffu,0x8000u,0x8001u,
        0xffffu,0x7fffffffu,0x80000000u,0x80000001u,0xfffffffeu,0xffffffffu};
    Bus strict;
    for(const auto& row:rows) {
      const unsigned bits=row[1]*8u;
      const unsigned mask=row[1]==4?0xffffffffu:(1u<<bits)-1u;
      const unsigned sign=1u<<(bits-1u);
      const unsigned samples=row[1]==1?256u:sizeof(boundaries)/sizeof(boundaries[0]);
      for(unsigned sample=0;sample<samples;++sample)for(unsigned x=0;x<2;++x)
       for(unsigned old_z=0;old_z<2;++old_z)for(unsigned known_z=0;known_z<2;++known_z) {
        const unsigned input=(row[1]==1?sample:boundaries[sample])&mask;
        const unsigned result=(0u-input-x)&mask;
        const bool borrow=input!=0||x!=0;
        const bool overflow=(input&sign)!=0&&(result&sign)!=0;
        const bool zero=result==0&&old_z!=0;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.d[row[2]]=0xa5a55a5au|input;cpu.d[row[2]]=(cpu.d[row[2]]&~mask)|input;
        cpu.d_known[row[2]]=mask;
        cpu.sr=static_cast<std::uint16_t>(0x2700u|(x<<4)|(old_z<<2)|3u);
        cpu.sr_known=static_cast<std::uint16_t>(0xffe0u|16u|(known_z<<2));
        const auto before=cpu;
        if(!step(cpu,strict)||cpu.stop!=Stop::none||cpu.pc!=row[0]+2||cpu.completed!=1)return 1;
        if(cpu.d[row[2]]!=((before.d[row[2]]&~mask)|result)||cpu.d_known[row[2]]!=mask)return 2;
        const unsigned flags=(borrow?17u:0u)|(result&sign?8u:0u)|
                             (zero?4u:0u)|(overflow?2u:0u);
        if(cpu.sr!=(0x2700u|flags))return 3;
        const unsigned expected_known=0xffe0u|27u|((result!=0||known_z)?4u:0u);
        if(cpu.sr_known!=expected_known)return 4;
        for(unsigned reg=0;reg<8;++reg)if(reg!=row[2]&&
          (cpu.d[reg]!=before.d[reg]||cpu.d_known[reg]!=before.d_known[reg]))return 5;
        if(cpu.a!=before.a||cpu.a_known!=before.a_known)return 6;
      }
    }
    return 0;
}
''')

    def test_unknown_inputs_and_invalid_helper_arguments_fail_without_result(self):
        sources = []
        for size in (1, 2, 4):
            source, _ = emit_cpp(negx(size, 3) + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated",
                                          f"negx_{size}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={negx_1::step,negx_2::step,negx_4::step};
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x89abcdefu;
    cpu.d_known[3]=0xffffffffu;cpu.sr=0x271fu;cpu.sr_known=0xffffu;return cpu;
}
int main() {
    Bus strict;
    const unsigned masks[]={0xffu,0xffffu,0xffffffffu};
    for(unsigned index=0;index<3;++index) {
        auto cpu=initial();cpu.d_known[3]&=~masks[index];const auto before=cpu;
        if(steps[index](cpu,strict)||cpu.stop!=Stop::undefined_state||
           !unchanged(cpu,before))return 1;
        cpu=initial();cpu.sr_known&=~16u;const auto before_x=cpu;
        if(steps[index](cpu,strict)||cpu.stop!=Stop::undefined_state||
           !unchanged(cpu,before_x))return 2;
    }
    for(unsigned bytes:{0u,3u,5u}) {
        auto cpu=initial();const auto before=cpu;
        if(negate_extend_data(cpu,bytes,3,2)||cpu.stop!=Stop::unsupported_instruction||
           !unchanged(cpu,before))return 3;
    }
    auto cpu=initial();const auto before=cpu;
    if(negate_extend_data(cpu,1,8,2)||cpu.stop!=Stop::unsupported_instruction||
       !unchanged(cpu,before))return 4;
    // A zero result legitimately retains an unknown incoming Z bit.
    cpu=initial();cpu.d[3]=0;cpu.sr=0x2700;cpu.sr_known=0xfffbu;
    if(!steps[0](cpu,strict)||cpu.d[3]!=0||cpu.sr!=0x2700||
       cpu.sr_known!=0xfffbu)return 5;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
