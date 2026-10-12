"""Native MC68000 MOVE.B/W/L (An)+,Dn coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move


class M68kPostincrementLoadTests(unittest.TestCase):
    def test_decoder_all_sizes_and_register_pairs(self):
        for size in (1, 2, 4):
            for source in range(8):
                for dest in range(8):
                    ins = decode(move(size, 3, source, 0, dest), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "move_memory_to_d",
                                      (size, 3, source, 0, dest)))

    def test_native_widths_wrap_a7_increment_destinations_flags_and_order(self):
        image = b"".join((move(1, 3, 7, 0, 0),
                          move(2, 3, 2, 0, 1),
                          move(4, 3, 3, 0, 2), words(0xffff)))
        source, report = emit_cpp(image, 0)
        self.assertEqual((report.translated, report.unsupported), (3, (6,)))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus{
    unsigned count=0;std::uint32_t address[2]{};
    std::uint8_t read8(std::uint32_t a)override{address[count++]=a;return 0x80u;}
    std::uint16_t read16(std::uint32_t a)override{
        address[count]=a;return count++?0x0001u:0x8000u;
    }
};
int main(){
    CPU cpu;reset_from_vectors(cpu,0x1234,0);cpu.d[0]=0xa5a55a5au;
    cpu.d_known[0]=0xffffff00u;cpu.sr=0x2717u;cpu.sr_known=0xffe0u;Reads bus;
    if(!step(cpu,bus)||cpu.a[7]!=0x1236u||cpu.d[0]!=0xa5a55a80u||
       cpu.d_known[0]!=0xffffffffu||cpu.sr!=0x2718u||cpu.sr_known!=0xffefu||
       bus.count!=1||bus.address[0]!=0x1234u)return 1;
    reset_from_vectors(cpu,0x2000,2);cpu.a[2]=0x00fffffeu;cpu.a_known[2]=true;
    cpu.d[1]=0xdead0000u;cpu.d_known[1]=0xffff0000u;cpu.sr=0x271fu;bus=Reads{};
    if(!step(cpu,bus)||cpu.a[2]!=0x01000000u||cpu.d[1]!=0xdead8000u||
       cpu.sr!=0x2718u||bus.count!=1||bus.address[0]!=0x00fffffeu)return 2;
    reset_from_vectors(cpu,0x2000,4);cpu.a[3]=0x00fffffeu;cpu.a_known[3]=true;
    cpu.d_known[2]=0;cpu.sr=0x271fu;bus=Reads{};
    if(!step(cpu,bus)||cpu.a[3]!=0x01000002u||cpu.d[2]!=0x80000001u||
       cpu.d_known[2]!=0xffffffffu||cpu.sr!=0x2718u||bus.count!=2||
       bus.address[0]!=0x00fffffeu||bus.address[1]!=0u)return 3;
    return 0;
}
''')

    def test_native_unknown_alignment_and_partial_faults_do_not_commit_cpu(self):
        source, _ = emit_cpp(move(4, 3, 3, 0, 2) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus{
    unsigned count=0,reject=0;
    std::uint16_t read16(std::uint32_t a)override{
        ++count;if(count==reject)throw BusFault(a,false,2);return count==1?0x1234u:0x5678u;
    }
};
bool same(const CPU&a,const CPU&b){
    return a.pc==b.pc&&a.sr==b.sr&&a.sr_known==b.sr_known&&a.d==b.d&&
           a.d_known==b.d_known&&a.a==b.a&&a.a_known==b.a_known&&
           a.completed==b.completed;
}
int main(){
    for(unsigned reject=1;reject<=2;++reject){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1000u;cpu.a_known[3]=true;
        cpu.d[2]=0xdeadbeefu;cpu.d_known[2]=0xffffffffu;cpu.sr=0x2715u;
        const CPU before=cpu;Reads bus;bus.reject=reject;
        if(step(cpu,bus)||cpu.stop!=Stop::bus_access||!same(cpu,before)||bus.count!=reject)return 1;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1001u;cpu.a_known[3]=true;
    const CPU odd=cpu;Reads bus;
    if(step(cpu,bus)||cpu.stop!=Stop::data_address||!same(cpu,odd)||bus.count||
       cpu.access_address!=0x1001u||cpu.access_width!=4u||cpu.access_write)return 2;
    reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x1000u;cpu.a_known[3]=false;
    const CPU unknown=cpu;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||!same(cpu,unknown)||bus.count)return 3;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
