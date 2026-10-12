"""Synthetic MC68000 MOVE and immediate shift/rotate coverage; no game bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def move(size, source_mode, source_reg, dest_mode, dest_reg, *extensions):
    opcode = {1: 0x1000, 2: 0x3000, 4: 0x2000}[size]
    return words(opcode | dest_reg << 9 | dest_mode << 6 | source_mode << 3 | source_reg,
                 *extensions)


def shift(size, reg, count, left, rotate):
    return words(0xe000 | (count % 8) << 9 | left << 8 | {1: 0, 2: 0x40, 4: 0x80}[size]
                 | (0x18 if rotate else 8) | reg)


def table(name, rows):
    return f"static const unsigned {name}[][" + str(len(rows[0])) + "]={" + ",".join(
        "{" + ",".join(f"{value}u" for value in row) + "}" for row in rows) + "};\n"


class M68kMovesShiftsTests(unittest.TestCase):
    def test_decoder_extensions_and_excluded_modes(self):
        image = move(1, 7, 4, 7, 1, 0xffa5, 0x1234, 0x5678)
        ins = decode(image, 0)
        self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                         (8, "move", (1, 1, 0xa5, 7, 1, 0x12345678)))
        self.assertEqual(decode(move(2, 7, 4, 5, 3, 0xfedc, 0xfff0), 0).operands,
                         (2, 1, 0xfedc, 5, 3, -16))
        self.assertEqual(decode(move(1, 0, 2, 7, 0, 0x8000), 0).operands,
                         (1, 0, 2, 7, 0, -32768))
        self.assertEqual(decode(move(4, 7, 4, 0, 7, 0x8765, 0x4321), 0).operands,
                         (4, 1, 0x87654321, 0, 7, 0))
        for image in (move(1, 1, 0, 0, 0), move(2, 4, 0, 0, 0),
                      move(2, 0, 0, 4, 0),
                      words(0xe020), words(0xe030), words(0xe0c0), words(0xe2c0),
                      words(0xe2a8), words(0xe018 | 0x20)):
            self.assertEqual(decode(image, 0).mnemonic, "unsupported")
        for image in (move(1, 7, 4, 7, 1), move(2, 7, 4, 5, 0, 0xffff),
                      move(4, 7, 4, 0, 0, 0xffff), move(1, 0, 0, 7, 0)):
            with self.assertRaises(ValueError):
                decode(image, 0)
        self.assertEqual(decode(shift(4, 1, 8, 0, True), 0).operands, (4, 1, 8, 0, 3))

    def test_moves_all_register_fields_sizes_aliases_and_immediates(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for source in range(8):
                for dest in range(8):
                    rows.append((len(image), size, source, dest))
                    image += move(size, 0, source, 0, dest)
        immediate_rows = []
        for size in (1, 2, 4):
            for dest in range(8):
                for value in (0, 1, (1 << (8 * size - 1)), (1 << (8 * size)) - 1):
                    immediate_rows.append((len(image), size, value, dest))
                    ext = (value >> 16, value & 0xffff) if size == 4 else (value,)
                    image += move(size, 7, 4, 0, dest, *ext)
        image += words(0xffff)
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + table("immediates", immediate_rows) + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for (const auto& row:rows) for(unsigned value:{0u,1u,0x80000080u,0xa5a58000u,0xffffffffu}) {
        const auto mask=row[1]==4?0xffffffffu:((1u<<(row[1]*8u))-1u);
        const auto sign=1u<<(row[1]*8u-1u);
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.sr=0x271fu;
        cpu.d[row[3]]=0xdeadbeef;cpu.d_known[row[3]]=0xff000000u;
        cpu.d[row[2]]=value;cpu.d_known[row[2]]=mask;
        const auto before=cpu.d[row[3]], known_before=cpu.d_known[row[3]];
        if(!step(cpu,bus))return 1;
        const auto part=value&mask;
        if(cpu.d[row[3]]!=((before&~mask)|part)||cpu.d_known[row[3]]!=(known_before|mask))return 2;
        if(cpu.sr!=(0x2710u|((part&sign)?8u:0u)|(part==0?4u:0u))||cpu.sr_known!=0xffefu)return 3;
        reset_from_vectors(cpu,0x2000,row[0]);cpu.d_known[row[2]]=mask&~1u;cpu.d[row[3]]=0x12345678;
        if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.completed||cpu.d[row[3]]!=0x12345678)return 4;
    }
    for(const auto& row:immediates) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[3]]=0x12345678;cpu.sr=0x270fu;
        const auto mask=row[1]==4?0xffffffffu:((1u<<(row[1]*8u))-1u);
        if(!step(cpu,bus)||cpu.d[row[3]]!=((0x12345678u&~mask)|row[2])||cpu.d_known[row[3]]!=mask)return 5;
        const auto flags=(row[2]&(1u<<(row[1]*8u-1u))?8u:0u)|(row[2]==0?4u:0u);
        if(cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffefu)return 6;
    }
    return 0;
}
''')

    def test_immediate_shifts_and_rotates_against_wide_integer_oracle(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for reg in range(8):
                for count in range(1, 9):
                    for left in (0, 1):
                        for rotate in (0, 1):
                            rows.append((len(image), size, reg, count, left, rotate))
                            image += shift(size, reg, count, left, rotate)
        image += words(0xffff)
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for(const auto& row:rows) for(unsigned sample=0;sample<(row[1]==1?256u:64u);++sample)
      for(unsigned x=0;x<2;++x) for(unsigned known_x=0;known_x<2;++known_x) {
        const unsigned bits=row[1]*8u,count=row[3];
        const std::uint64_t modulus=std::uint64_t{1}<<bits, mask=modulus-1u;
        const unsigned full=row[1]==1 ? 0xa5a50000u|sample : sample*0x9e3779b9u;
        const std::uint64_t value=full&mask;
        std::uint64_t result;
        const bool carry=row[4] ? ((value>>(bits-count))&1u)!=0 : ((value>>(count-1u))&1u)!=0;
        if(row[5]) result=row[4] ? ((value<<count)|(value>>(bits-count)))&mask
                                            : ((value>>count)|(value<<(bits-count)))&mask;
        else result=row[4] ? (value<<count)&mask : value>>count;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.d[row[2]]=full;cpu.d_known[row[2]]=static_cast<unsigned>(mask);
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xffffu:0xffefu);
        if(!step(cpu,bus))return 1;
        const unsigned flags=(result&(modulus>>1)?8u:0u)|(result==0?4u:0u)|(carry?1u:0u);
        const unsigned expected_x=row[5]?x:static_cast<unsigned>(carry);
        if(cpu.d[row[2]]!=((full&~static_cast<unsigned>(mask))|result)||cpu.sr!=(0x2700u|flags|(expected_x<<4)))return 2;
        if(cpu.sr_known!=((known_x||!row[5])?0xffffu:0xffefu)||cpu.d_known[row[2]]!=mask)return 3;
    }
    for(const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[2]]=0xdeadbeef;cpu.d_known[row[2]]=0xfffffffeu;
        if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.d[row[2]]!=0xdeadbeef||cpu.pc!=row[0])return 4;
    }
    return 0;
}
''')

    def test_move_memory_width_alignment_and_write_faults(self):
        cases = [move(1, 7, 4, 7, 1, 0xffa5, 0x1234, 0x5679),
                 move(2, 7, 4, 7, 1, 0x80fe, 0x1234, 0x5678),
                 move(1, 0, 7, 5, 2, 0xfffe),
                 move(2, 0, 7, 5, 2, 0xfffe),
                 move(1, 0, 7, 7, 0, 0xfffe),
                 move(2, 0, 7, 7, 0, 0xfffe)]
        sources = []
        for index, image in enumerate(cases):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"memory_{index}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={memory_0::step,memory_1::step,memory_2::step,memory_3::step,memory_4::step,memory_5::step};
struct Writes:Bus {
    unsigned count=0,width=0,address=0,value=0;bool reject=false;
    void record(unsigned a,unsigned v,unsigned w) {
        ++count;address=a;value=v;width=w;if(reject)throw BusFault(a,true,static_cast<std::uint8_t>(w));
    }
    void write8(std::uint32_t a,std::uint8_t v)override{record(a,v,1);}
    void write16(std::uint32_t a,std::uint16_t v)override{record(a,v,2);}
};
int main() {
    const unsigned addresses[]={0x345679,0x345678,0xfffffe,0xfffffe,0xfffffe,0xfffffe};
    const unsigned sizes[]={8,8,4,4,4,4},values[]={0xa5,0x80fe,0x81,0x8081,0x81,0x8081};
    for(unsigned i=0;i<6;++i)for(unsigned reject=0;reject<2;++reject) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[2]=0x01000000;cpu.a_known[2]=true;
        cpu.d[7]=0xa5a58081;cpu.d_known[7]=0xffff;cpu.sr=0x271f;cpu.sr_known=0xffff;
        Writes bus;bus.reject=reject;
        if(steps[i](cpu,bus)==bool(reject)||bus.count!=1||bus.width!=(i%2+1)||bus.address!=addresses[i]||bus.value!=values[i])return 1;
        if(reject) {
            if(cpu.pc||cpu.completed||cpu.sr!=0x271f||cpu.stop!=Stop::bus_access||cpu.access_width!=(i%2+1)||!cpu.access_write)return 2;
        } else if(cpu.pc!=sizes[i]||cpu.completed!=1||cpu.sr!=0x2718)return 3;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[2]=3;cpu.a_known[2]=true;cpu.d_known[7]=0xffff;
    Writes bus;
    if(steps[3](cpu,bus)||bus.count||cpu.stop!=Stop::data_address||cpu.access_address!=1||cpu.access_width!=2)return 4;
    reset_from_vectors(cpu,0x2000,0);cpu.d_known[7]=0xffff;
    if(steps[2](cpu,bus)||bus.count||cpu.stop!=Stop::undefined_state)return 5;
    reset_from_vectors(cpu,0x2000,0);Bus strict;
    if(steps[1](cpu,strict)||cpu.stop!=Stop::bus_access||cpu.access_width!=2||cpu.access_address!=0x345678)return 6;
    try{(void)strict.read16(0x100400);return 7;}catch(const BusFault& e){if(e.width!=2||e.write)return 8;}
    return 0;
}
''')

    def test_clear_can_discard_unknown_data_without_omitting_read_transaction(self):
        source, _ = emit_cpp(words(0x422a, 2, 0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct DiscardOnly:Bus {
    unsigned reads=0,writes=0;
    void read8_discard(std::uint32_t address)override {
        if(address!=0x2345)throw BusFault(address,false);
        ++reads; // Synthetic device has a documented read with unused unknown data.
    }
    void write8(std::uint32_t address,std::uint8_t value)override {
        if(address!=0x2345||reads!=1||value!=0)throw BusFault(address,true);
        ++writes;
    }
};
int main() {
    DiscardOnly bus;
    try{(void)bus.read8(0x2345);return 1;}catch(const BusFault& e){if(e.write)return 2;}
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[2]=0x2343;cpu.a_known[2]=true;
    if(!step(cpu,bus)||bus.reads!=1||bus.writes!=1||cpu.pc!=4||cpu.sr!=0x2704)return 3;
    reset_from_vectors(cpu,0x2000,0);cpu.a[2]=0x2344;cpu.a_known[2]=true;
    if(step(cpu,bus)||bus.reads!=1||bus.writes!=1||cpu.stop!=Stop::bus_access||
       cpu.access_address!=0x2346||cpu.access_write||cpu.pc!=0)return 4;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
