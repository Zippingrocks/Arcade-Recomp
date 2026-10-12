"""Native MC68000 OR.B/W/L Dn,Dn semantics."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def or_data(size, source, destination):
    return words(0x8000 | destination << 9 |
                 {1: 0, 2: 0x40, 4: 0x80}[size] | source)


class M68KOrDataNativeTest(unittest.TestCase):
    def test_decode_all_widths_and_registers(self):
        for size in (1, 2, 4):
            for source in range(8):
                for destination in range(8):
                    ins = decode(or_data(size, source, destination), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "or_d", (size, source, destination)))
        self.assertEqual(decode(words(0x80c0), 0).mnemonic, "unsupported")

    def test_values_aliases_flags_knownness_and_atomic_refusal(self):
        image = b"".join(or_data(size, source, destination)
                         for size in (1, 2, 4)
                         for source in range(8) for destination in range(8))
        source, report = emit_cpp(image + words(0xffff), 0)
        self.assertEqual(report.translated, 192)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
int main(){
 const unsigned values[]={0u,1u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,0xffffu,
                          0x12345678u,0x80000000u,0xffffffffu};
 unsigned pc=0;
 for(unsigned bytes:{1u,2u,4u})for(unsigned src=0;src<8u;++src)for(unsigned dst=0;dst<8u;++dst,pc+=2u){
  const unsigned mask=bytes==4u?0xffffffffu:(1u<<(bytes*8u))-1u;
  for(unsigned left:values)for(unsigned right:values){CPU c;reset_from_vectors(c,0x2000u,pc);
   c.d[src]=left;c.d_known[src]=mask;c.d[dst]=right;c.d_known[dst]=mask;c.sr=0x2713u;c.sr_known=0xffe0u;
   const unsigned source_value=src==dst?right:left;
   const unsigned expected=(source_value|right)&mask,upper=right&~mask;Bus b;
   if(!step(c,b)||c.d[dst]!=(upper|expected)||c.d_known[dst]!=mask||c.pc!=pc+2u||c.completed!=1u)return 1;
   const unsigned flags=(expected&(1u<<(bytes*8u-1u))?8u:0u)|(expected==0u?4u:0u);
   if((c.sr&0x1fu)!=(0x10u|flags)||(c.sr_known&0x1fu)!=0x0fu)return 2;
  }
 }
 for(unsigned which=0;which<2u;++which){CPU c;reset_from_vectors(c,0x2000u,130u);c.d[0]=1u;c.d[1]=2u;
  c.d_known[0]=c.d_known[1]=0xffffu;c.d_known[which]=0xffu;const auto before=c;Bus b;
  if(step(c,b)||c.stop!=Stop::undefined_state||c.d!=before.d||c.sr!=before.sr||c.completed)return 3;}
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
