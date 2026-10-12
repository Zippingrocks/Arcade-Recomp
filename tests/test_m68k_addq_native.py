"""Native MC68000 ADDQ-to-data-register coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def addq(size, immediate, reg):
    return words(0x5000 | (immediate & 7) << 9 |
                 {1: 0, 2: 0x40, 4: 0x80}[size] | reg)


class M68kAddQuickTests(unittest.TestCase):
    def test_decoder_all_sizes_immediates_registers_and_boundaries(self):
        for size in (1, 2, 4):
            for immediate in range(1, 9):
                for reg in range(8):
                    ins = decode(addq(size, immediate, reg), 0x1000, 0x1000)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "addq_d", (size, reg, immediate)))
        self.assertEqual(decode(words(0x5002), 0).operands, (1, 2, 8))
        for opcode in (0x5100, 0x5048, 0x5050, 0x50c0, 0x50c8):
            self.assertNotEqual(decode(words(opcode, 0), 0).mnemonic, "addq_d")

    def test_native_byte_exhaustive_and_wide_boundaries_against_oracle(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for immediate in range(1, 9):
                for reg in range(8):
                    rows.append((len(image), size, immediate, reg))
                    image += addq(size, immediate, reg)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main(){
    for(const auto& row:rows){
        const unsigned bits=row[1]*8u;
        const std::uint64_t modulus=std::uint64_t{1}<<bits,mask=modulus-1u,sign=modulus>>1u;
        const unsigned samples=row[1]==1?256u:8u;
        for(unsigned i=0;i<samples;++i){
            const std::uint64_t candidates[]={i,0u,1u,sign-1u,sign,mask-7u,mask-1u,mask};
            const std::uint64_t value=row[1]==1?i:candidates[i];
            const std::uint64_t wide=value+row[2],result=wide&mask;
            const bool carry=wide>mask;
            const bool overflow=((~(value^row[2])&(value^result)&sign)!=0);
            const unsigned flags=(carry?0x11u:0u)|(result&sign?8u:0u)|
                                 (result==0?4u:0u)|(overflow?2u:0u);
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
            const unsigned upper=row[1]==1?0xa5a55a00u:row[1]==2?0xa5a50000u:0u;
            cpu.d[row[3]]=upper|static_cast<unsigned>(value);
            cpu.d_known[row[3]]=static_cast<unsigned>(mask);cpu.sr=0x271fu;cpu.sr_known=0xffe0u;
            Bus bus;if(!step(cpu,bus))return 1;
            const unsigned expected=upper|static_cast<unsigned>(result);
            if(cpu.d[row[3]]!=expected||cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu)return 2;
        }
    }
    return 0;
}
''')

    def test_unknown_inputs_and_direct_helper_arguments_fail_atomically(self):
        source, _ = emit_cpp(addq(2, 8, 3) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
int main(){
    Bus bus;CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x1234ffff;cpu.d_known[3]=0xfffffffe;
    cpu.sr=0x2715;const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.d[3]!=before.d[3]||
       cpu.sr!=before.sr||cpu.pc||cpu.completed)return 1;
    for(unsigned bytes:{0u,3u,5u}){
        reset_from_vectors(cpu,0x2000,0);if(add_quick_data(cpu,bytes,0,1,2)||
          cpu.stop!=Stop::unsupported_instruction)return 2;
    }
    for(unsigned immediate:{0u,9u}){
        reset_from_vectors(cpu,0x2000,0);if(add_quick_data(cpu,1,0,immediate,2)||
          cpu.stop!=Stop::unsupported_instruction)return 3;
    }
    reset_from_vectors(cpu,0x2000,0);if(add_quick_data(cpu,1,8,1,2)||
      cpu.stop!=Stop::unsupported_instruction)return 4;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
