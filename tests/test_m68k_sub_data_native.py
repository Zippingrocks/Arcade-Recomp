"""Native MC68000 SUB.B/W/L Dn,Dn coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def sub(size, source, dest):
    return words(0x9000 | dest << 9 | {1: 0, 2: 0x40, 4: 0x80}[size] |
                 source)


class M68kSubtractDataTests(unittest.TestCase):
    def test_decoder_all_sizes_register_pairs_and_subset_boundaries(self):
        for size in (1, 2, 4):
            for source in range(8):
                for dest in range(8):
                    ins = decode(sub(size, source, dest), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "sub_d", (size, source, dest)))
        for opcode in (0x90c0, 0x91c0, 0x9100, 0x9108, 0x9010, 0x9050):
            self.assertNotEqual(decode(words(opcode), 0).mnemonic, "sub_d")

    def test_native_register_pairs_boundaries_and_exhaustive_byte_oracle(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for source in range(8):
                for dest in range(8):
                    rows.append((len(image), size, source, dest))
                    image += sub(size, source, dest)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
unsigned flags(unsigned bits,unsigned source,unsigned destination){
    const std::uint64_t modulus=std::uint64_t{1}<<bits,mask=modulus-1u,sign=modulus>>1u;
    source&=static_cast<unsigned>(mask);destination&=static_cast<unsigned>(mask);
    const unsigned result=static_cast<unsigned>((destination-source)&mask);
    const bool borrow=destination<source;
    const bool overflow=((destination^source)&(destination^result)&sign)!=0;
    return (borrow?17u:0u)|(result&sign?8u:0u)|(result==0?4u:0u)|(overflow?2u:0u);
}
int main(){
    const unsigned values[]={0u,1u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,
                             0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};
    for(const auto& row:rows)for(unsigned source:values)for(unsigned destination:values){
        const unsigned bits=row[1]*8u,mask=row[1]==4?0xffffffffu:(1u<<bits)-1u;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.d[row[2]]=source;cpu.d_known[row[2]]=mask;
        cpu.d[row[3]]=destination;cpu.d_known[row[3]]=mask;
        const unsigned actual_source=cpu.d[row[2]]&mask;
        const unsigned actual_destination=cpu.d[row[3]]&mask;
        cpu.sr=0x271fu;cpu.sr_known=0xffe0u;Bus bus;
        const unsigned result=(actual_destination-actual_source)&mask;
        if(!step(cpu,bus)||(cpu.d[row[3]]&mask)!=result||
           cpu.sr!=(0x2700u|flags(bits,actual_source,actual_destination))||
           cpu.sr_known!=0xffffu)return 1;
    }
    const auto& row=rows[1];
    for(unsigned source=0;source<256;++source)for(unsigned destination=0;destination<256;++destination){
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[2]]=source;
        cpu.d_known[row[2]]=0xffu;cpu.d[row[3]]=destination;cpu.d_known[row[3]]=0xffu;
        Bus bus;if(!step(cpu,bus)||cpu.d[row[3]]!=((destination-source)&0xffu)||
          cpu.sr!=(0x2700u|flags(8,source,destination)))return 2;
    }
    return 0;
}
''')

    def test_unknown_operands_and_invalid_helper_arguments_fail_atomically(self):
        source, _ = emit_cpp(sub(2, 3, 6) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
bool same(const CPU&a,const CPU&b){
    return a.pc==b.pc&&a.sr==b.sr&&a.sr_known==b.sr_known&&a.d==b.d&&
           a.d_known==b.d_known&&a.a==b.a&&a.a_known==b.a_known&&
           a.completed==b.completed;
}
int main(){
    for(unsigned unknown:{3u,6u}){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x1234u;cpu.d[6]=0x5678u;
        cpu.d_known[3]=cpu.d_known[6]=0xffffu;cpu.d_known[unknown]=0xfffeu;
        const CPU before=cpu;Bus bus;
        if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||!same(cpu,before))return 1;
    }
    for(unsigned bytes:{0u,3u,5u}){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);
        if(subtract_data(cpu,bytes,0,1,2)||cpu.stop!=Stop::unsupported_instruction)return 2;
    }
    for(unsigned reg:{8u,9u}){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);
        if(subtract_data(cpu,1,reg,0,2)||cpu.stop!=Stop::unsupported_instruction)return 3;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
