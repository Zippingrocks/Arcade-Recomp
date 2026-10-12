"""Native MC68000 register-count LSL/LSR coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def logical_shift(size, destination, count_register, left, kind=1):
    return words(0xe020 | count_register << 9 | left << 8 |
                 {1: 0, 2: 0x40, 4: 0x80}[size] | kind << 3 |
                 destination)


class M68kLogicalShiftRegisterTests(unittest.TestCase):
    def test_decoder_all_fields_widths_directions_and_exclusions(self):
        for size in (1, 2, 4):
            for destination in range(8):
                for count_register in range(8):
                    for left in (0, 1):
                        ins = decode(logical_shift(size, destination,
                                                   count_register, left), 0)
                        self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                         (2, "logical_shift_register",
                                          (size, destination, count_register,
                                           left)))
                    for kind in (0, 2, 3):
                        self.assertNotEqual(
                            decode(logical_shift(size, destination,
                                                 count_register, 0, kind), 0).mnemonic,
                            "logical_shift_register")
        self.assertEqual(decode(words(0xe0e0), 0).mnemonic, "unsupported")

    def test_native_register_pairs_aliases_counts_widths_and_exact_flags(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for destination in range(8):
                for count_register in range(8):
                    for left in (0, 1):
                        rows.append((len(image), size, destination,
                                     count_register, left))
                        image += logical_shift(size, destination,
                                               count_register, left)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][5]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned values[]={0u,1u,2u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,
        0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};
    const unsigned counts[]={0u,1u,7u,8u,9u,15u,16u,17u,31u,32u,33u,63u,64u,65u};
    Bus strict;
    for(const auto& row:rows)for(unsigned requested:values)for(unsigned requested_count:counts)
      for(unsigned x=0;x<2;++x)for(unsigned known_x=0;known_x<2;++known_x) {
        const unsigned bits=row[1]*8u;
        const unsigned mask=row[1]==4?0xffffffffu:(1u<<bits)-1u;
        const unsigned sign=1u<<(bits-1u);
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.d[row[2]]=(0xa5a55a5au&~mask)|(requested&mask);cpu.d_known[row[2]]=mask;
        cpu.d[row[3]]=requested_count;cpu.d_known[row[3]]|=63u;
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xffffu:0xffefu);
        const auto before=cpu;
        unsigned value=before.d[row[2]]&mask,count=before.d[row[3]]&63u;bool carry=false;
        for(unsigned i=0;i<count;++i){carry=(value&(row[4]?sign:1u))!=0;
          value=row[4]?(value<<1u)&mask:value>>1u;}
        if(!step(cpu,strict)||cpu.stop!=Stop::none||cpu.pc!=row[0]+2||cpu.completed!=1)return 1;
        if(cpu.d[row[2]]!=((before.d[row[2]]&~mask)|value)||
           cpu.d_known[row[2]]!=(before.d_known[row[2]]|mask))return 2;
        const unsigned flags=(value&sign?8u:0u)|(value==0?4u:0u)|
                             (count&&carry?1u:0u)|(count?(carry?16u:0u):x<<4);
        if(cpu.sr!=(0x2700u|flags))return 3;
        const unsigned expected_known=(count||known_x)?0xffffu:0xffefu;
        if(cpu.sr_known!=expected_known)return 4;
        for(unsigned reg=0;reg<8;++reg)if(reg!=row[2]&&
          (cpu.d[reg]!=before.d[reg]||cpu.d_known[reg]!=before.d_known[reg]))return 5;
    }
    return 0;
}
''')

    def test_exhaustive_byte_oracle_unknown_inputs_and_invalid_arguments(self):
        native('#include "m68k_runtime.hpp"\n', r'''
using namespace arcaderecomp::m68k;
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[1]=0x12345678u;
    cpu.d[2]=0;cpu.d_known[1]=0xffu;cpu.d_known[2]=63u;
    cpu.sr=0x271fu;cpu.sr_known=0xffffu;return cpu;
}
int main() {
    for(unsigned input=0;input<256;++input)for(unsigned count=0;count<64;++count)
      for(unsigned left=0;left<2;++left)for(unsigned x=0;x<2;++x) {
        auto cpu=initial();cpu.d[1]=(cpu.d[1]&~0xffu)|input;cpu.d[2]=count;
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));unsigned value=input;bool carry=false;
        for(unsigned i=0;i<count;++i){carry=(value&(left?0x80u:1u))!=0;
          value=left?(value<<1u)&0xffu:value>>1u;}
        if(!logical_shift_register(cpu,1,1,2,left!=0,2)||cpu.d[1]!=(0x12345600u|value))return 1;
        const unsigned flags=(value&0x80u?8u:0u)|(value==0?4u:0u)|
                             (count&&carry?1u:0u)|(count?(carry?16u:0u):x<<4);
        if(cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu)return 2;
    }
    for(unsigned which=0;which<2;++which) {
        auto cpu=initial();if(which)cpu.d_known[2]&=~1u;else cpu.d_known[1]&=~1u;
        const auto before=cpu;
        if(logical_shift_register(cpu,1,1,2,false,2)||
           cpu.stop!=Stop::undefined_state||!unchanged(cpu,before))return 3;
    }
    for(unsigned bytes:{0u,3u,5u}) {
        auto cpu=initial();const auto before=cpu;
        if(logical_shift_register(cpu,bytes,1,2,false,2)||
           cpu.stop!=Stop::unsupported_instruction||!unchanged(cpu,before))return 4;
    }
    for(unsigned destination:{8u,9u})for(unsigned count_register:{2u,8u})
      if(destination>=8u||count_register>=8u) {
        auto cpu=initial();const auto before=cpu;
        if(logical_shift_register(cpu,1,destination,count_register,false,2)||
           cpu.stop!=Stop::unsupported_instruction||!unchanged(cpu,before))return 5;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
