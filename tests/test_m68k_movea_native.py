"""Native MC68000 MOVEA source-mode coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move


class M68kMoveAddressTests(unittest.TestCase):
    def test_decoder_sizes_modes_extensions_and_exclusions(self):
        for size in (2, 4):
            for source_mode in (0, 1, 2):
                for source in range(8):
                    for dest in range(8):
                        ins = decode(move(size, source_mode, source, 1, dest), 0)
                        self.assertEqual(ins.operands,
                                         (size, source_mode, source, dest, 0))
            self.assertEqual(decode(move(size, 5, 3, 1, 2, 0xfffe), 0).operands,
                             (size, 5, 3, 2, -2))
            self.assertEqual(decode(move(size, 7, 0, 1, 2, 0x8000), 0).operands,
                             (size, 7, 0, 2, -32768))
            self.assertEqual(decode(move(size, 7, 1, 1, 2, 0x1234, 0x5678), 0).operands,
                             (size, 7, 1, 2, 0x12345678))
        self.assertEqual(decode(move(2, 7, 4, 1, 2, 0x8000), 0).operands,
                         (2, 7, 4, 2, 0x8000))
        self.assertEqual(decode(move(4, 7, 4, 1, 2, 0x89ab, 0xcdef), 0).operands,
                         (4, 7, 4, 2, 0x89abcdef))
        for image in (move(1, 0, 0, 1, 0), move(4, 3, 0, 1, 0),
                      move(4, 4, 0, 1, 0), move(4, 6, 0, 1, 0, 0),
                      move(4, 7, 2, 1, 0, 0), move(4, 7, 3, 1, 0, 0)):
            self.assertEqual(decode(image, 0).mnemonic, "unsupported")

    def test_native_register_immediate_sign_extension_and_flags(self):
        images = [move(4, 0, 3, 1, 2), move(2, 0, 3, 1, 2),
                  move(4, 1, 3, 1, 2), move(2, 1, 3, 1, 2),
                  move(4, 7, 4, 1, 2, 0x89ab, 0xcdef),
                  move(2, 7, 4, 1, 2, 0x8001)]
        sources = []
        for i, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"case_{i}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={case_0::step,case_1::step,case_2::step,case_3::step,case_4::step,case_5::step};
int main(){
    const unsigned expected[]={0x89abcdefu,0xffffcdefu,0x76543210u,0x00003210u,0x89abcdefu,0xffff8001u};
    for(unsigned i=0;i<6;++i){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x89abcdef;cpu.d_known[3]=0xffffffff;
        cpu.a[3]=0x76543210;cpu.a_known[3]=true;cpu.sr=0x271f;cpu.sr_known=0xffe5;
        Bus bus;if(!steps[i](cpu,bus)||cpu.a[2]!=expected[i]||!cpu.a_known[2]||
           cpu.sr!=0x271f||cpu.sr_known!=0xffe5)return 1;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[3]=0x12345678;cpu.d_known[3]=0xffff;
    Bus bus;if(steps[0](cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.a_known[2])return 2;
    reset_from_vectors(cpu,0x2000,0);if(steps[2](cpu,bus)||cpu.stop!=Stop::undefined_state)return 3;
    return 0;
}
''')

    def test_native_memory_addresses_width_order_and_refusals(self):
        images = [move(4, 2, 3, 1, 2), move(2, 5, 3, 1, 2, 0xfffe),
                  move(4, 7, 0, 1, 2, 0x8000),
                  move(4, 7, 1, 1, 2, 0x1234, 0x5678)]
        sources = []
        for i, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"memory_{i}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={memory_0::step,memory_1::step,memory_2::step,memory_3::step};
struct Reads:Bus{
    unsigned count=0,address[2]{},reject=0;
    std::uint16_t read16(std::uint32_t a)override{
        address[count]=a;++count;if(count==reject)throw BusFault(a,false,2);
        return count==1?0x8001:0x2345;
    }
};
int main(){
    const unsigned addresses[]={0x1000,0x0ffe,0xff8000,0x345678};
    const unsigned expected[]={0x80012345,0xffff8001,0x80012345,0x80012345};
    for(unsigned i=0;i<4;++i){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1000;cpu.a_known[3]=true;
        cpu.sr=0x271f;cpu.sr_known=0xffff;Reads bus;
        if(!steps[i](cpu,bus)||cpu.a[2]!=expected[i]||cpu.sr!=0x271f||
           bus.address[0]!=addresses[i]||bus.count!=(i==1?1u:2u))return 1;
        if(i!=1&&bus.address[1]!=((addresses[i]+2u)&0xffffffu))return 2;
    }
    for(unsigned reject=1;reject<=2;++reject){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1000;cpu.a_known[3]=true;
        cpu.a[2]=0xdeadbeef;cpu.a_known[2]=false;Reads bus;bus.reject=reject;
        if(steps[0](cpu,bus)||cpu.stop!=Stop::bus_access||cpu.a[2]!=0xdeadbeef||
           cpu.a_known[2]||bus.count!=reject)return 3;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1001;cpu.a_known[3]=true;Reads bus;
    if(steps[0](cpu,bus)||cpu.stop!=Stop::data_address||bus.count)return 4;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
