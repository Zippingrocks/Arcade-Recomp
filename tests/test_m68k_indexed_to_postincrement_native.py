"""Native MC68000 MOVE d8(An,Xn),(Am)+ transaction and alias semantics."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_indexed_native import extension
from test_m68k_moves_shifts_native import move


class M68KIndexedToPostincrementNativeTest(unittest.TestCase):
    def test_decode_all_widths_registers_and_reserved_extensions(self):
        for size in (1, 2, 4):
            for base in range(8):
                for destination in range(8):
                    ext = extension((base + 1) & 7, long=bool(destination & 1),
                                    displacement=destination - 4)
                    ins = decode(move(size, 6, base, 3, destination, ext), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                        (4, "move_indexed_to_postincrement",
                         (size, base, destination, ext)))
        self.assertEqual(decode(move(2, 6, 1, 3, 0, 0x0100), 0).mnemonic,
                         "unsupported")
        with self.assertRaises(ValueError):
            decode(words(0x30f1), 0)

    def test_native_source_first_alias_increment_flags_and_refusals(self):
        source, report = emit_cpp(move(2, 6, 1, 3, 0, 0x0000) + words(0xffff), 0)
        self.assertEqual((report.translated, report.unsupported), (1, (4,)))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Events:Bus {
 unsigned count=0,deny=0,address[2]{},width[2]{},write[2]{};
 void hit(unsigned a,unsigned w,bool out){address[count]=a;width[count]=w;write[count]=out;
  ++count;if(count==deny)throw BusFault(a,out,static_cast<std::uint8_t>(w));}
 std::uint16_t read16(std::uint32_t a)override{hit(a,2,false);return 0x8001u;}
 void write16(std::uint32_t a,std::uint16_t)override{hit(a,2,true);}
};
CPU initial(){CPU c;reset_from_vectors(c,0x2000u,0u);c.a[0]=0x2000u;c.a[1]=0x1000u;
 c.a_known[0]=c.a_known[1]=true;c.d[0]=4u;c.d_known[0]=0xffffu;c.sr=0x2710u;return c;}
int main(){
 {auto c=initial();Events b;if(!step(c,b)||b.count!=2u||b.address[0]!=0x1004u||b.write[0]||
    b.address[1]!=0x2000u||!b.write[1]||c.a[0]!=0x2002u||c.pc!=4u||c.completed!=1u||
    (c.sr&0x1fu)!=0x18u)return 1;}
 // A0 is both source base and postincrement destination: source resolution
 // observes its original value, while the increment commits after writing.
 {auto c=initial();c.a[0]=0x1000u;c.d[1]=2u;c.d_known[1]=0xffffu;Events b;
  if(!arcaderecomp::m68k::move_indexed_to_postincrement(c,b,2u,0u,0u,0x1000u,4u)||
    b.address[0]!=0x1002u||b.address[1]!=0x1000u||c.a[0]!=0x1002u)return 2;}
 {auto c=initial();c.d_known[0]=0u;auto before=c;Events b;if(step(c,b)||
    c.stop!=Stop::undefined_state||b.count||c.a!=before.a||c.completed)return 3;}
 // Destination knownness is consumed after the accepted source read.
 {auto c=initial();c.a_known[0]=false;Events b;if(step(c,b)||c.stop!=Stop::undefined_state||
    b.count!=1u||b.write[0]||c.a[0]!=0x2000u||c.completed)return 4;}
 for(unsigned denial=1;denial<=2;++denial){auto c=initial();Events b;b.deny=denial;
  if(step(c,b)||c.stop!=Stop::bus_access||b.count!=denial||c.a[0]!=0x2000u||c.completed||
     c.access_write!=(denial==2u))return 5;}
 {auto c=initial();c.a[0]=1u;Events b;if(step(c,b)||c.stop!=Stop::data_address||
    b.count!=1u||c.a[0]!=1u||c.completed||!c.access_write)return 6;}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
