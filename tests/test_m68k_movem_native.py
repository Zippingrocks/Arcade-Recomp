"""Native original-MC68000 MOVEM store and postincrement-load coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def movem_store(size, base, mask, predecrement=False):
    return words(0x4880 | (0x40 if size == 4 else 0) |
                 (4 if predecrement else 2) << 3 | base, mask)


def movem_load(size, base, mask):
    return words(0x4c80 | (0x40 if size == 4 else 0) | 3 << 3 | base,
                 mask)


class M68kMoveMultipleTests(unittest.TestCase):
    def test_decoder_sizes_bases_masks_directions_exclusions_and_truncation(self):
        for size in (2, 4):
            for base in range(8):
                for mask in (0, 1, 0x80, 0x100, 0x8000, 0x19ff, 0xffd8,
                             0xffff):
                    for predecrement in (False, True):
                        ins = decode(movem_store(size, base, mask,
                                                 predecrement), 0)
                        self.assertEqual(
                            (ins.size, ins.mnemonic, ins.operands),
                            (4, "movem_store",
                             (size, base, mask, predecrement)))
                    ins = decode(movem_load(size, base, mask), 0)
                    self.assertEqual(
                        (ins.size, ins.mnemonic, ins.operands),
                        (4, "movem_load_postincrement", (size, base, mask)))
        for opcode in (0x4898, 0x48d8, 0x4c90, 0x4ca0, 0x4cd0):
            self.assertEqual(decode(words(opcode, 0xffff), 0).mnemonic,
                             "unsupported")
        for opcode in (0x4890, 0x48a0, 0x4c98, 0x4cd8):
            with self.assertRaises(ValueError):
                decode(words(opcode), 0)

    def test_native_control_mode_store_normal_order_values_and_immutability(self):
        image, rows = bytearray(), []
        masks = (0, 1, 0x81, 0x0101, 0x8080, 0xffff)
        for size in (2, 4):
            for base in range(8):
                for mask in masks:
                    rows.append((len(image), size, base, mask))
                    image += movem_store(size, base, mask)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Writes:Bus {
    unsigned count=0,addresses[32]{},values[32]{};
    void write16(std::uint32_t a,std::uint16_t v)override{addresses[count]=a;values[count++]=v;}
};
int main() {
    for (const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for (unsigned reg=0;reg<8u;++reg){cpu.d[reg]=0xd0000000u+reg*0x101u+reg;
          cpu.d_known[reg]=0xffffffffu;cpu.a[reg]=0xa0001000u+reg*0x100u;
          cpu.a_known[reg]=true;}
        cpu.sr=0x271bu;cpu.sr_known=0xffe5u;const auto before=cpu;Writes bus;
        if (!step(cpu,bus)||cpu.pc!=row[0]+4u||cpu.completed!=1u||
            cpu.d!=before.d||cpu.a!=before.a||cpu.sr!=before.sr||
            cpu.sr_known!=before.sr_known) return 1;
        unsigned event=0,address=before.a[row[2]]&0xffffffu;
        for (unsigned bit=0;bit<16u;++bit) {
            if (!(row[3]&(1u<<bit))) continue;
            const unsigned value=bit<8u?before.d[bit]:before.a[bit-8u];
            if (row[1]==2u) {
                if (bus.addresses[event]!=address||bus.values[event]!=(value&0xffffu)) return 2;
                ++event;address=(address+2u)&0xffffffu;
            } else {
                if (bus.addresses[event]!=address||bus.values[event]!=(value>>16u)) return 3;
                ++event;address=(address+2u)&0xffffffu;
                if (bus.addresses[event]!=address||bus.values[event]!=(value&0xffffu)) return 4;
                ++event;address=(address+2u)&0xffffffu;
            }
        }
        if (bus.count!=event) return 5;
    }
    return 0;
}
''')

    def test_native_predecrement_reverse_mask_order_and_original_base_value(self):
        image, rows = bytearray(), []
        masks = (0, 1, 0x80, 0x100, 0x8000, 0x8081, 0xffd8,
                 0xffff)
        for size in (2, 4):
            for base in range(8):
                for mask in masks:
                    rows.append((len(image), size, base, mask))
                    image += movem_store(size, base, mask, True)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Writes:Bus {unsigned count=0,addresses[32]{},values[32]{};
 void write16(std::uint32_t a,std::uint16_t v)override{addresses[count]=a;values[count++]=v;}};
int main() {
    for (const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for (unsigned reg=0;reg<8u;++reg){cpu.d[reg]=0xd0000000u+reg*0x101u+reg;
          cpu.d_known[reg]=0xffffffffu;cpu.a[reg]=0x00101000u+reg*0x100u;
          cpu.a_known[reg]=true;}
        cpu.sr=0x271bu;cpu.sr_known=0xffe5u;const auto before=cpu;Writes bus;
        if (!step(cpu,bus)||cpu.pc!=row[0]+4u||cpu.completed!=1u||
            cpu.d!=before.d||cpu.sr!=before.sr||cpu.sr_known!=before.sr_known) return 1;
        unsigned selected=0;for(unsigned bit=0;bit<16u;++bit)if(row[3]&(1u<<bit))++selected;
        if (cpu.a[row[2]]!=before.a[row[2]]-selected*row[1]) return 2;
        unsigned event=0,address=before.a[row[2]]&0xffffffu;
        for (unsigned bit=0;bit<16u;++bit) {
            if (!(row[3]&(1u<<bit))) continue;
            const bool ar=bit<8u;const unsigned reg=ar?7u-bit:15u-bit;
            const unsigned value=ar?before.a[reg]:before.d[reg];
            address=(address-row[1])&0xffffffu;
            if (row[1]==2u) {
                if (bus.addresses[event]!=address||bus.values[event]!=(value&0xffffu)) return 3;
                ++event;
            } else {
                if (bus.addresses[event]!=address||bus.values[event]!=(value>>16u)) return 4;
                ++event;
                if (bus.addresses[event]!=((address+2u)&0xffffffu)||
                    bus.values[event]!=(value&0xffffu)) return 5;
                ++event;
            }
        }
        if (bus.count!=event) return 6;
    }
    return 0;
}
''')

    def test_native_postincrement_load_sign_extension_base_ignore_and_partial_commit(self):
        image, rows = bytearray(), []
        for size in (2, 4):
            for base in range(8):
                rows.append((len(image), size, base))
                image += movem_load(size, base, 0xffff)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][3]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0,transfer=0,half=0,deny=0,bytes=4,addresses[32]{};
    std::uint16_t read16(std::uint32_t a)override {
        addresses[count]=a;++count;if(count==deny)throw BusFault(a,false,2);
        if(bytes==2u)return static_cast<std::uint16_t>(0x8000u+transfer++);
        const unsigned value=0x80000000u+transfer;
        if (half==0u){half=1u;return static_cast<std::uint16_t>(value>>16u);}
        half=0u;++transfer;return static_cast<std::uint16_t>(value);
    }
};
int main() {
    for (const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned reg=0;reg<8u;++reg){cpu.d[reg]=0xdead0000u+reg;cpu.d_known[reg]=0;
          cpu.a[reg]=0x2000u+reg*0x100u;cpu.a_known[reg]=true;}
        cpu.sr=0x271bu;cpu.sr_known=0xffe5u;const auto before=cpu;Reads bus;
        bus.bytes=row[1];
        if(!step(cpu,bus)||cpu.pc!=row[0]+4u||cpu.completed!=1u||
           cpu.sr!=before.sr||cpu.sr_known!=before.sr_known) return 1;
        for(unsigned bit=0;bit<16u;++bit){const unsigned expected=row[1]==2u?
          (0xffff8000u+bit):(0x80000000u+bit);
          if(bit<8u){if(cpu.d[bit]!=expected||cpu.d_known[bit]!=0xffffffffu)return 2;}
          else if(bit-8u!=row[2]){if(cpu.a[bit-8u]!=expected||!cpu.a_known[bit-8u])return 3;}}
        if(cpu.a[row[2]]!=before.a[row[2]]+16u*row[1])return 4;
    }
    // A refused third word transfer retains the first two completed loads and
    // their postincrements, but does not commit the refused destination.
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[0]=0x2000;cpu.a_known[0]=true;
    cpu.d.fill(0xdeadbeefu);cpu.d_known.fill(0);const auto before=cpu;Reads failing;
    failing.bytes=2u;failing.deny=3u;
    if(step(cpu,failing)||cpu.stop!=Stop::bus_access||cpu.d[0]!=0xffff8000u||
       cpu.d[1]!=0xffff8001u||cpu.d[2]!=before.d[2]||cpu.a[0]!=0x2004u||
       cpu.pc!=before.pc||cpu.completed!=before.completed)return 5;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
