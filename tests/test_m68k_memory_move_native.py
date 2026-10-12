"""Native MC68000 memory-to-memory postincrement MOVE coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move


class M68kMemoryMoveTests(unittest.TestCase):
    def test_decoder_all_sizes_registers_and_subset_boundary(self):
        for size in (1, 2, 4):
            for source in range(8):
                for destination in range(8):
                    ins = decode(move(size, 3, source, 3, destination), 0x1000,
                                 0x1000)
                    self.assertEqual(
                        (ins.size, ins.mnemonic, ins.operands),
                        (2, "move_memory_postincrement",
                         (size, source, destination)))
        self.assertEqual(decode(move(4, 2, 0, 3, 1), 0).mnemonic,
                         "unsupported")
        self.assertEqual(decode(move(4, 3, 0, 2, 1), 0).mnemonic,
                         "unsupported")

    def test_native_bus_order_aliases_flags_and_a7_byte_increment(self):
        image = b"".join((move(4, 3, 0, 3, 1), move(1, 3, 7, 3, 7),
                          move(2, 3, 2, 3, 2), words(0xffff)))
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.unsupported, (6,))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Memory:Bus {
    unsigned reads=0,writes=0;std::uint32_t ra[4]{},wa[4]{};
    std::uint16_t rv[4]{0x8000,1,0,0},wv[4]{};
    std::uint8_t read8(std::uint32_t a)override{ra[reads++]=a;return 0;}
    std::uint16_t read16(std::uint32_t a)override{ra[reads]=a;return rv[reads++];}
    void write8(std::uint32_t a,std::uint8_t v)override{wa[writes]=a;wv[writes++]=v;}
    void write16(std::uint32_t a,std::uint16_t v)override{wa[writes]=a;wv[writes++]=v;}
};
int main(){
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x1000;cpu.a[1]=0x2000;
    cpu.a_known[0]=cpu.a_known[1]=true;cpu.sr=0x2717;cpu.sr_known=0xffff;
    Memory bus;
    if(!step(cpu,bus)||cpu.a[0]!=0x1004||cpu.a[1]!=0x2004||cpu.pc!=2)return 1;
    if(bus.reads!=2||bus.ra[0]!=0x1000||bus.ra[1]!=0x1002||
       bus.writes!=2||bus.wa[0]!=0x2000||bus.wa[1]!=0x2002||
       bus.wv[0]!=0x8000||bus.wv[1]!=1||cpu.sr!=0x2718)return 2;
    reset_from_vectors(cpu,0x3000,2);cpu.a[7]=0x3000;cpu.a_known[7]=true;
    bus=Memory{};
    if(!step(cpu,bus)||cpu.a[7]!=0x3004||bus.ra[0]!=0x3000||
       bus.wa[0]!=0x3002||cpu.sr!=0x2704)return 3;
    reset_from_vectors(cpu,0x4000,4);cpu.a[2]=0x4000;cpu.a_known[2]=true;
    bus=Memory{};bus.rv[0]=0x1234;
    if(!step(cpu,bus)||cpu.a[2]!=0x4004||bus.ra[0]!=0x4000||
       bus.wa[0]!=0x4002||bus.wv[0]!=0x1234)return 4;
    return 0;
}
''')

    def test_native_unknown_alignment_and_partial_fault_observability(self):
        source, _ = emit_cpp(move(4, 3, 0, 3, 1) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Faults:Bus {
    unsigned reads=0,writes=0,reject_read=0,reject_write=0;
    std::uint16_t read16(std::uint32_t a)override{
        ++reads;if(reads==reject_read)throw BusFault(a,false,2);return reads==1?0x1234:0x5678;
    }
    void write16(std::uint32_t a,std::uint16_t)override{
        ++writes;if(writes==reject_write)throw BusFault(a,true,2);
    }
};
int main(){
    for(unsigned reject=1;reject<=2;++reject){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x1000;cpu.a[1]=0x2000;
        cpu.a_known[0]=cpu.a_known[1]=true;Faults bus;bus.reject_read=reject;
        if(step(cpu,bus)||cpu.stop!=Stop::bus_access||cpu.a[0]!=0x1000||
           cpu.a[1]!=0x2000||bus.reads!=reject||bus.writes)return 1;
    }
    for(unsigned reject=1;reject<=2;++reject){
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x1000;cpu.a[1]=0x2000;
        cpu.a_known[0]=cpu.a_known[1]=true;Faults bus;bus.reject_write=reject;
        if(step(cpu,bus)||cpu.stop!=Stop::bus_access||cpu.a[0]!=0x1004||
           cpu.a[1]!=0x2000||bus.reads!=2||bus.writes!=reject)return 2;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x1001;cpu.a[1]=0x2000;
    cpu.a_known[0]=cpu.a_known[1]=true;Faults bus;
    if(step(cpu,bus)||cpu.stop!=Stop::data_address||cpu.access_address!=0x1001||
       cpu.access_write||cpu.access_width!=4||bus.reads)return 3;
    reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x1000;cpu.a[1]=0x2001;
    cpu.a_known[0]=cpu.a_known[1]=true;
    if(step(cpu,bus)||cpu.stop!=Stop::data_address||cpu.access_address!=0x2001||
       !cpu.access_write||cpu.access_width!=4||cpu.a[0]!=0x1004||bus.reads!=2)return 4;
    reset_from_vectors(cpu,0x2000,0);cpu.a_known[0]=true;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||bus.reads!=2)return 5;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
