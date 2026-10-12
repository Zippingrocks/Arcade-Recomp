"""Native MC68000 immediate BTST coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def btst(bit, mode, reg, *extensions):
    return words(0x0800 | mode << 3 | reg, bit, *extensions)


class M68kBitTestImmediateTests(unittest.TestCase):
    def test_decoder_modes_extensions_modulo_inputs_and_exclusions(self):
        cases = ((0, 3, (), 0, 4), (2, 4, (), 0, 4),
                 (5, 6, (0xfffe,), -2, 6),
                 (7, 0, (0x8000,), -32768, 6),
                 (7, 1, (0x1234, 0x5678), 0x12345678, 8))
        for bit in (0, 1, 7, 8, 31, 32, 255, 0xffff):
            for mode, reg, extensions, displacement, length in cases:
                ins = decode(btst(bit, mode, reg, *extensions), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (length, "btst_immediate",
                                  (bit, mode, reg, displacement)))
        for mode, reg in ((1, 0), (3, 0), (4, 0), (6, 0),
                          (7, 2), (7, 3), (7, 4)):
            self.assertNotEqual(decode(btst(0, mode, reg), 0).mnemonic,
                                "btst_immediate")
        for image in (words(0x0800), btst(0, 5, 0),
                      btst(0, 7, 1, 0x1234)):
            with self.assertRaises(ValueError):
                decode(image, 0)

    def test_native_modulo_bits_register_partial_knownness_memory_and_flags(self):
        image, rows = bytearray(), []
        for bit in (0, 1, 7, 8, 31, 32, 63, 255):
            for mode in (0, 2, 5):
                for reg in range(8):
                    displacement = -2 if mode == 5 else 0
                    length = 6 if mode == 5 else 4
                    rows.append((len(image), bit, mode, reg,
                                 displacement, length))
                    image += btst(bit, mode, reg,
                                  *((0xfffe,) if mode == 5 else ()))
            rows.append((len(image), bit, 7, 0, -2, 6))
            image += btst(bit, 7, 0, 0xfffe)
            rows.append((len(image), bit, 7, 1, 0x00ffffff, 8))
            image += btst(bit, 7, 1, 0x00ff, 0xffff)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][6]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Read:Bus{unsigned calls=0,address=0,value=0;std::uint8_t read8(std::uint32_t a)override{
 address=a;++calls;return static_cast<std::uint8_t>(value);}};
int main(){
 for(const auto& row:rows)for(unsigned set=0;set<2;++set)
  for(unsigned flags=0;flags<32;++flags)for(unsigned known=0;known<32;++known){
   const unsigned bit=row[1]&(row[2]==0?31u:7u),mask=1u<<bit;
   CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);for(unsigned i=0;i<8;++i){
    cpu.a[i]=0x12001000u+i*4u;cpu.a_known[i]=true;cpu.d[i]=set?mask:0;cpu.d_known[i]=mask;}
   cpu.sr=static_cast<std::uint16_t>(0x2700u|flags);cpu.sr_known=static_cast<std::uint16_t>(0xffe0u|known);
   const auto before=cpu;Read bus;bus.value=set?mask:0;
   if(!step(cpu,bus)||cpu.pc!=row[0]+row[5]||cpu.completed!=1)return 1;
   if(bus.calls!=(row[2]==0?0u:1u))return 2;
   if(row[2]!=0){const unsigned logical=row[2]==7?row[4]:before.a[row[3]]+row[4];
    if(bus.address!=(logical&0xffffffu))return 3;}
   const unsigned expected=(before.sr&~4u)|(set?0u:4u);
   if(cpu.sr!=expected||cpu.sr_known!=(before.sr_known|4u))return 4;
   if(cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a!=before.a||cpu.a_known!=before.a_known)return 5;
  }
 return 0;}
''')

    def test_unknown_selected_bit_base_and_refused_read_are_uncommitted(self):
        images = (btst(31, 0, 3), btst(2, 2, 4),
                  btst(7, 7, 1, 0x00ff, 0xffff))
        sources = []
        for index, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"btst_{index}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;using Step=bool(*)(CPU&,Bus&);
Step steps[]={btst_0::step,btst_1::step,btst_2::step};
struct Read:Bus{unsigned calls=0;bool reject=false;std::uint8_t read8(std::uint32_t a)override{
 ++calls;if(reject)throw BusFault(a,false,1);return 0x80;}};
bool same(const CPU&c,const CPU&b){return c.d==b.d&&c.a==b.a&&c.d_known==b.d_known&&
 c.a_known==b.a_known&&c.sr==b.sr&&c.sr_known==b.sr_known&&c.pc==b.pc&&c.completed==b.completed;}
CPU init(){CPU c;reset_from_vectors(c,0x2000,0);c.d[3]=0x80000000;c.d_known[3]=0x80000000;
 c.a[4]=0x1000;c.a_known[4]=true;c.sr=0x271f;c.sr_known=0xffe0;return c;}
int main(){auto c=init();c.d_known[3]=0;auto b=c;Read bus;if(steps[0](c,bus)||c.stop!=Stop::undefined_state||bus.calls||!same(c,b))return 1;
 c=init();c.a_known[4]=false;b=c;if(steps[1](c,bus)||c.stop!=Stop::undefined_state||bus.calls||!same(c,b))return 2;
 for(unsigned i=1;i<3;++i){c=init();b=c;Read fail;fail.reject=true;if(steps[i](c,fail)||
  c.stop!=Stop::bus_access||fail.calls!=1||!same(c,b)||c.access_write||c.access_width!=1)return 3;}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
