"""Native MC68000 memory ADDQ/BSET and register-source MULU coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


SIZE_BITS = {1: 0, 2: 0x40, 4: 0x80}


def extensions(mode, reg, displacement):
    if mode == 5 or (mode, reg) == (7, 0):
        return (displacement & 0xffff,)
    if (mode, reg) == (7, 1):
        return (displacement >> 16, displacement & 0xffff)
    return ()


def addq_memory(size, immediate, mode, reg, displacement=0):
    return words(0x5000 | (immediate & 7) << 9 | SIZE_BITS[size] |
                 mode << 3 | reg, *extensions(mode, reg, displacement))


def bset_memory(bit, mode, reg, displacement=0):
    return words(0x08c0 | mode << 3 | reg, bit,
                 *extensions(mode, reg, displacement))


def mulu(source, destination, mode=0):
    return words(0xc0c0 | destination << 9 | mode << 3 | source)


def lea_pc_indexed(destination, ext):
    return words(0x41fb | destination << 9, ext)


class M68kSimpleFrontierTests(unittest.TestCase):
    def test_pc_indexed_lea_decoder_and_native_addresses(self):
        extensions = (0x0000, 0x087f, 0x3080, 0xb8ff)
        image, rows = bytearray(), []
        for destination in range(8):
            for ext in extensions:
                ins = decode(lea_pc_indexed(destination, ext), 0x1000,
                             0x1000)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (4, "lea_pc_indexed", (destination, ext)))
                rows.append((len(image), destination, ext))
                image += lea_pc_indexed(destination, ext)
        self.assertEqual(decode(lea_pc_indexed(0, 0x0100), 0).mnemonic,
                         "unsupported")
        with self.assertRaises(ValueError):
            decode(words(0x41fb), 0)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][3]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus strict;
    for (const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for (unsigned reg=0;reg<8u;++reg){cpu.d[reg]=0x12348000u+reg;
          cpu.d_known[reg]=0xffffffffu;cpu.a[reg]=0x23458000u+reg;cpu.a_known[reg]=true;}
        cpu.sr=0x271bu;cpu.sr_known=0xffe5u;const auto before=cpu;
        const unsigned index=(row[2]>>12u)&7u;
        unsigned value=(row[2]&0x8000u)?before.a[index]:before.d[index];
        if (!(row[2]&0x0800u)) value=(value&0x8000u)?
            ((value&0xffffu)|0xffff0000u):(value&0xffffu);
        const unsigned byte=row[2]&0xffu;
        const unsigned displacement=byte&0x80u?byte|0xffffff00u:byte;
        const unsigned expected=row[0]+2u+value+displacement;
        if (!step(cpu,strict)||cpu.a[row[1]]!=expected||!cpu.a_known[row[1]]||
            cpu.sr!=before.sr||cpu.sr_known!=before.sr_known||cpu.pc!=row[0]+4u) return 1;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d_known[0]=0xfffeu;
    const auto before=cpu;
    if (step(cpu,strict)||cpu.stop!=Stop::undefined_state||cpu.a!=before.a||
        cpu.pc!=before.pc||cpu.completed!=before.completed) return 2;
    return 0;
}
''')

    def test_decoder_fields_forms_extensions_exclusions_and_truncation(self):
        forms = ((2, 3, 0, 2), (5, 4, -2, 4),
                 (7, 0, -32768, 4), (7, 1, 0x12345678, 6))
        for size in (1, 2, 4):
            for immediate in range(1, 9):
                for mode, reg, displacement, length in forms:
                    ins = decode(addq_memory(size, immediate, mode, reg,
                                             displacement), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (length, "addq_memory",
                                      (size, mode, reg, displacement,
                                       immediate)))
        for bit in (0, 1, 7, 8, 31, 255, 0xffff):
            for mode, reg, displacement, length in forms:
                ins = decode(bset_memory(bit, mode, reg, displacement), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (length + 2, "bset_immediate_memory",
                                  (bit, mode, reg, displacement)))
        for source in range(8):
            for destination in range(8):
                ins = decode(mulu(source, destination), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (2, "mulu_d", (source, destination)))
        for mode in (0, 1, 3, 4, 6):
            self.assertNotEqual(decode(addq_memory(2, 1, mode, 0), 0).mnemonic,
                                "addq_memory")
        for mode in (0, 1, 3, 4, 6):
            self.assertNotEqual(decode(bset_memory(2, mode, 0), 0).mnemonic,
                                "bset_immediate_memory")
        for mode in range(1, 8):
            self.assertNotEqual(decode(mulu(0, 0, mode), 0).mnemonic, "mulu_d")
        for image in (addq_memory(2, 1, 5, 0)[:2],
                      bset_memory(2, 5, 0)[:4]):
            with self.assertRaises(ValueError):
                decode(image, 0)

    def test_native_addq_and_bset_memory_rmw_values_flags_and_order(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        for size in (1, 2, 4):
            for immediate in range(1, 9):
                for mode, reg, displacement in forms:
                    data = addq_memory(size, immediate, mode, reg, displacement)
                    rows.append((len(image), 0, size, immediate, mode, reg,
                                 displacement, len(data)))
                    image += data
        for bit in (0, 1, 7, 8, 31, 255):
            for mode, reg, displacement in forms:
                data = bset_memory(bit, mode, reg, displacement)
                rows.append((len(image), 1, 1, bit, mode, reg,
                             displacement, len(data)))
                image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][8]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct RMW:Bus {
    unsigned count=0,reads=0,bytes=0,value=0,addresses[4]{},values[4]{};bool writes[4]{};
    void record(unsigned a,unsigned v,bool write){addresses[count]=a;values[count]=v;
      writes[count]=write;++count;}
    std::uint8_t read8(std::uint32_t a)override{record(a,value,false);++reads;return static_cast<std::uint8_t>(value);}
    std::uint16_t read16(std::uint32_t a)override{const unsigned v=bytes==4u&&reads==0u?value>>16u:value;
      record(a,v,false);++reads;return static_cast<std::uint16_t>(v);}
    void write8(std::uint32_t a,std::uint8_t v)override{record(a,v,true);}
    void write16(std::uint32_t a,std::uint16_t v)override{record(a,v,true);}
};
int main() {
    const unsigned inputs[]={0u,1u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,
                             0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};
    for (const auto& row:rows) {
        for (unsigned raw:inputs) {
            const unsigned bits=row[2]*8u;
            const unsigned mask=row[2]==4u?0xffffffffu:(1u<<bits)-1u;
            const unsigned sign=1u<<(bits-1u),value=raw&mask;
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.a[row[5]]=2u;
            cpu.a_known[row[5]]=true;cpu.sr=0x271bu;cpu.sr_known=0xffe3u;
            const auto before=cpu;RMW bus;bus.bytes=row[2];bus.value=value;
            if (!step(cpu,bus)||cpu.pc!=row[0]+row[7]||cpu.completed!=1u) return 1;
            const unsigned logical=row[4]==7u?row[6]:before.a[row[5]]+row[6];
            const unsigned address=logical&0xffffffu,half=row[2]==4u?2u:1u;
            if (bus.count!=half*2u||bus.addresses[0]!=address||bus.writes[0]||
                !bus.writes[half]) return 2;
            if (row[1]==0u) {
                const unsigned result=(value+row[3])&mask;
                const bool carry=static_cast<std::uint64_t>(value)+row[3]>mask;
                const bool overflow=(~(value^row[3])&(value^result)&sign)!=0u;
                const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|
                                     (result==0u?4u:0u)|(overflow?2u:0u);
                if (bus.values[half]!=(row[2]==4u?result>>16u:result)||
                    cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu) return 3;
            } else {
                const unsigned selected=row[3]&7u,bit=1u<<selected;
                if (bus.values[half]!=(value|bit)||
                    cpu.sr!=((before.sr&~4u)|((value&bit)?0u:4u))||
                    cpu.sr_known!=(before.sr_known|4u)) return 4;
            }
            if (cpu.d!=before.d||cpu.a!=before.a) return 5;
        }
    }
    return 0;
}
''')

    def test_native_mulu_all_registers_aliases_boundaries_and_knownness(self):
        image, rows = bytearray(), []
        for source in range(8):
            for destination in range(8):
                rows.append((len(image), source, destination))
                image += mulu(source, destination)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][3]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned values[]={0u,1u,2u,0x7fffu,0x8000u,0xfffeu,0xffffu};
    Bus strict;
    for (const auto& row:rows) {
        for (unsigned left:values) {
            for (unsigned right:values) {
                CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
                cpu.d[row[1]]=left;cpu.d_known[row[1]]=0xffffu;
                cpu.d[row[2]]=right;cpu.d_known[row[2]]=0xffffu;
                const unsigned source_value=cpu.d[row[1]]&0xffffu;
                const unsigned destination_value=cpu.d[row[2]]&0xffffu;
                const unsigned result=source_value*destination_value;
                cpu.sr=0x271fu;cpu.sr_known=0xffefu;
                if (!step(cpu,strict)||cpu.d[row[2]]!=result||
                    cpu.d_known[row[2]]!=0xffffffffu) return 1;
                const unsigned flags=(result&0x80000000u?8u:0u)|(result==0u?4u:0u);
                if (cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffefu) return 2;
            }
        }
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d_known[row[1]]=0xffffu;
        cpu.d_known[row[2]]=0xffffu;cpu.d_known[row[1]]&=~1u;const auto before=cpu;
        if (step(cpu,strict)||cpu.stop!=Stop::undefined_state||cpu.d!=before.d||
            cpu.pc!=before.pc||cpu.completed!=before.completed) return 3;
    }
    CPU cpu;
    if (multiply_unsigned_word(cpu,8u,0u,2u)||
        cpu.stop!=Stop::unsupported_instruction) return 4;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
