"""Native MC68000 ADDA.W/L Dn,An coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def adda(size, source, dest):
    return words(0xd000 | dest << 9 | (0xc0 if size == 2 else 0x1c0) |
                 source)


class M68kAddAddressDataTests(unittest.TestCase):
    def test_decoder_all_sizes_register_pairs_and_subset_boundaries(self):
        for size in (2, 4):
            for source in range(8):
                for dest in range(8):
                    ins = decode(adda(size, source, dest), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "adda_d", (size, source, dest)))
        for opcode in (0xd000, 0xd080, 0xd0c8, 0xd0d0, 0xd1c8, 0xd1d0):
            self.assertNotEqual(decode(words(opcode), 0).mnemonic, "adda_d")

    def test_native_register_pairs_boundaries_wrap_and_unchanged_flags(self):
        image, rows = bytearray(), []
        for size in (2, 4):
            for source in range(8):
                for dest in range(8):
                    rows.append((len(image), size, source, dest))
                    image += adda(size, source, dest)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main(){
    const unsigned inputs[]={0u,1u,0x7fffu,0x8000u,0xffffu,
                             0x7fffffffu,0x80000000u,0xffffffffu};
    const unsigned destinations[]={0u,1u,0x7fffffffu,0x80000000u,0xffffffffu};
    for(const auto& row:rows)for(unsigned input:inputs)for(unsigned base:destinations){
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[2]]=input;
        cpu.d_known[row[2]]=row[1]==2?0xffffu:0xffffffffu;
        cpu.a[row[3]]=base;cpu.a_known[row[3]]=true;
        cpu.sr=0x2715u;cpu.sr_known=0xffe5u;Bus bus;
        const unsigned value=row[1]==2?
          ((input&0x8000u)?(input|0xffff0000u):(input&0xffffu)):input;
        if(!step(cpu,bus)||cpu.a[row[3]]!=base+value||!cpu.a_known[row[3]]||
           cpu.d[row[2]]!=input||cpu.sr!=0x2715u||cpu.sr_known!=0xffe5u)return 1;
    }
    return 0;
}
''')

    def test_unknown_selected_source_or_destination_fails_atomically(self):
        images = (adda(2, 3, 2), adda(4, 3, 2))
        sources = []
        for i, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated",
                                          f"case_{i}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);Step steps[]={case_0::step,case_1::step};
bool same(const CPU&a,const CPU&b){
    return a.pc==b.pc&&a.sr==b.sr&&a.sr_known==b.sr_known&&a.d==b.d&&
           a.d_known==b.d_known&&a.a==b.a&&a.a_known==b.a_known&&
           a.completed==b.completed;
}
int main(){
    for(unsigned i=0;i<2;++i){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x12345678u;
        cpu.d_known[3]=(i?0xfffffffeu:0xfffeu);cpu.a[2]=0xabcdef01u;
        cpu.a_known[2]=true;const CPU before=cpu;Bus bus;
        if(steps[i](cpu,bus)||cpu.stop!=Stop::undefined_state||!same(cpu,before))return 1;
        reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x12345678u;
        cpu.d_known[3]=i?0xffffffffu:0xffffu;cpu.a[2]=0xabcdef01u;
        cpu.a_known[2]=false;const CPU unknown=cpu;
        if(steps[i](cpu,bus)||cpu.stop!=Stop::undefined_state||!same(cpu,unknown))return 2;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
