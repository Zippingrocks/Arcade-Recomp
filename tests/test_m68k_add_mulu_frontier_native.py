"""Native MC68000 register/memory ADD and immediate MULU frontier."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


SIZE_BITS = {1: 0, 2: 0x40, 4: 0x80}


def add_d(size, source, destination):
    return words(0xd000 | destination << 9 | SIZE_BITS[size] | source)


def add_d_memory(size, source, mode, reg, displacement=0):
    extension = ()
    if mode == 5 or (mode, reg) == (7, 0):
        extension = (displacement & 0xffff,)
    elif mode == 6:
        extension = (displacement & 0xffff,)
    elif (mode, reg) == (7, 1):
        extension = (displacement >> 16, displacement & 0xffff)
    return words(0xd100 | source << 9 | SIZE_BITS[size] | mode << 3 | reg,
                 *extension)


def sub_d_memory(size, source, mode, reg, displacement=0):
    data = add_d_memory(size, source, mode, reg, displacement)
    return words(int.from_bytes(data[:2], "big") - 0x4000,
                 *(int.from_bytes(data[i:i + 2], "big")
                   for i in range(2, len(data), 2)))


def mulu_immediate(source, destination):
    return words(0xc0fc | destination << 9, source)


class M68kAddMuluFrontierTests(unittest.TestCase):
    def test_decoder_fields_extensions_exclusions_and_truncation(self):
        forms = ((2, 3, 0, 2), (5, 4, -2, 4),
                 (7, 0, -32768, 4), (7, 1, 0x12345678, 6))
        for size in (1, 2, 4):
            for source in range(8):
                for destination in range(8):
                    ins = decode(add_d(size, source, destination), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "add_d",
                                      (size, source, destination)))
                for mode, reg, displacement, length in forms:
                    for builder, mnemonic in (
                            (add_d_memory, "add_d_to_memory"),
                            (sub_d_memory, "sub_d_to_memory")):
                        ins = decode(builder(size, source, mode, reg,
                                             displacement), 0)
                        self.assertEqual(
                            (ins.size, ins.mnemonic, ins.operands),
                            (length, mnemonic,
                             (size, source, mode, reg, displacement)))
                for base in range(8):
                    for extension in (0x0002, 0x78fc, 0x8006, 0xf8fe):
                        for builder, mnemonic in (
                                (add_d_memory, "add_d_to_indexed"),
                                (sub_d_memory, "sub_d_to_indexed")):
                            ins = decode(builder(size, source, 6, base,
                                                 extension), 0)
                            self.assertEqual(
                                (ins.size, ins.mnemonic, ins.operands),
                                (4, mnemonic,
                                 (size, source, base, extension)))
        for source in (0, 1, 0x7fff, 0x8000, 0xffff):
            for destination in range(8):
                ins = decode(mulu_immediate(source, destination), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (4, "mulu_immediate",
                                  (source, destination)))
        for mode in (0, 1, 3, 4, 6):
            if mode != 6:
                self.assertNotEqual(
                    decode(add_d_memory(2, 0, mode, 0), 0).mnemonic,
                    "add_d_to_memory")
                self.assertNotEqual(
                    decode(sub_d_memory(2, 0, mode, 0), 0).mnemonic,
                    "sub_d_to_memory")
        for image in (add_d_memory(4, 0, 5, 0)[:2],
                      sub_d_memory(4, 0, 5, 0)[:2],
                      add_d_memory(4, 0, 6, 0)[:2],
                      sub_d_memory(4, 0, 6, 0)[:2],
                      mulu_immediate(1, 0)[:2]):
            with self.assertRaises(ValueError):
                decode(image, 0)

    def test_native_register_add_and_immediate_mulu(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for source in range(8):
                for destination in range(8):
                    rows.append((len(image), 0, size, source, destination, 2))
                    image += add_d(size, source, destination)
        for immediate in (0, 1, 2, 0x7fff, 0x8000, 0xffff):
            for destination in range(8):
                rows.append((len(image), 1, 2, immediate, destination, 4))
                image += mulu_immediate(immediate, destination)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][6]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main(){
  const unsigned samples[]={0u,1u,2u,0x7fu,0x80u,0xffu,0x7fffu,0x8000u,
    0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};Bus strict;
  for(const auto& row:rows)for(unsigned raw:samples){CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
    for(unsigned r=0;r<8u;++r){cpu.d[r]=samples[(raw+r)%12u];cpu.d_known[r]=0xffffffffu;}
    cpu.d[row[4]]=raw;cpu.sr=0x271fu;cpu.sr_known=0xffe0u;const auto before=cpu;
    if(!step(cpu,strict)||cpu.pc!=row[0]+row[5]||cpu.completed!=1u)return 1;
    if(row[1]==0u){const unsigned bits=row[2]*8u;
      const unsigned mask=row[2]==4u?0xffffffffu:(1u<<bits)-1u,sign=1u<<(bits-1u);
      const unsigned sv=before.d[row[3]]&mask,dv=before.d[row[4]]&mask,result=(dv+sv)&mask;
      const bool carry=static_cast<std::uint64_t>(dv)+sv>mask;
      const bool overflow=(~(dv^sv)&(dv^result)&sign)!=0u;
      const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|(result==0u?4u:0u)|(overflow?2u:0u);
      if(cpu.d[row[4]]!=((before.d[row[4]]&~mask)|result)||cpu.sr!=(0x2700u|flags)||
         cpu.sr_known!=0xffffu)return 2;
    }else{const unsigned result=(row[3]&0xffffu)*(before.d[row[4]]&0xffffu);
      const unsigned flags=(result&0x80000000u?8u:0u)|(result==0u?4u:0u);
      if(cpu.d[row[4]]!=result||cpu.d_known[row[4]]!=0xffffffffu||
         cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffefu)return 3;}
  }
  CPU cpu;Bus bus;if(add_data(cpu,3,0,0,2)||cpu.stop!=Stop::unsupported_instruction)return 4;
  cpu=CPU{};if(multiply_unsigned_word_immediate(cpu,0x10000u,0,2)||
    cpu.stop!=Stop::unsupported_instruction)return 5;
  return 0;
}
''')

    def test_native_data_to_memory_rmw_values_flags_and_refusals(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        for size in (1, 2, 4):
            for source in range(8):
                for mode, reg, displacement in forms:
                    data = add_d_memory(size, source, mode, reg,
                                        displacement)
                    rows.append((len(image), size, source, mode, reg,
                                 displacement, len(data)))
                    image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][7]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct RMW:Bus{unsigned count=0,reads=0,bytes=0,value=0,deny=0,addresses[4]{},values[4]{};bool writes[4]{};
 void record(unsigned a,unsigned v,bool w){addresses[count]=a;values[count]=v;writes[count]=w;
   ++count;if(count==deny)throw BusFault(a,w,bytes==1u?1u:2u);}
 std::uint8_t read8(std::uint32_t a)override{record(a,value,false);++reads;return static_cast<std::uint8_t>(value);}
 std::uint16_t read16(std::uint32_t a)override{const unsigned v=bytes==4u&&reads==0u?value>>16u:value;
   record(a,v,false);++reads;return static_cast<std::uint16_t>(v);}
 void write8(std::uint32_t a,std::uint8_t v)override{record(a,v,true);}
 void write16(std::uint32_t a,std::uint16_t v)override{record(a,v,true);}};
int main(){const unsigned pairs[][2]={{0,0},{1,1},{0x7f,1},{0x7f,0x80},
 {0xffff,1},{0x7fffffff,1},{0x80000000,0x80000000},{0xffffffff,1}};
 for(const auto& row:rows)for(const auto& pair:pairs){const unsigned bits=row[1]*8u;
  const unsigned mask=row[1]==4u?0xffffffffu:(1u<<bits)-1u,sign=1u<<(bits-1u);
  const unsigned destination=pair[0]&mask,sv=pair[1]&mask,result=(destination+sv)&mask;
  CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[2]]=sv;cpu.d_known[row[2]]=mask;
  cpu.a[row[4]]=2;cpu.a_known[row[4]]=true;cpu.sr=0x271f;cpu.sr_known=0xffe0;
  const auto before=cpu;RMW bus;bus.bytes=row[1];bus.value=destination;
  if(!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1u)return 1;
  const unsigned address=(row[3]==7u?row[5]:before.a[row[4]]+row[5])&0xffffffu;
  const unsigned half=row[1]==4u?2u:1u;if(bus.count!=half*2u||bus.addresses[0]!=address||
    bus.writes[0]||!bus.writes[half]||bus.values[half]!=(row[1]==4u?result>>16u:result))return 2;
  const bool carry=static_cast<std::uint64_t>(destination)+sv>mask;
  const bool overflow=(~(destination^sv)&(destination^result)&sign)!=0u;
  const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|(result==0u?4u:0u)|(overflow?2u:0u);
  if(cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu||cpu.d!=before.d||cpu.a!=before.a)return 3;
 }
 CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d[0]=1;cpu.d_known[0]=0xff;
 cpu.a[2]=2;cpu.a_known[2]=true;const auto before=cpu;RMW failing;failing.bytes=1;failing.value=1;failing.deny=2;
 if(step(cpu,failing)||cpu.stop!=Stop::bus_access||cpu.sr!=before.sr||cpu.pc!=before.pc||
   cpu.completed!=before.completed||failing.count!=2u)return 4;
 return 0;}
''')

    def test_native_subtract_and_indexed_memory_directions(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        indexed = (0x0002, 0x78fc, 0x8006, 0xf8fe)
        for size in (1, 2, 4):
            for source in range(8):
                for mode, reg, displacement in forms:
                    data = sub_d_memory(size, source, mode, reg,
                                        displacement)
                    rows.append((len(image), 0, size, source, mode, reg,
                                 displacement, len(data)))
                    image += data
                for base in range(8):
                    for extension in indexed:
                        for kind, builder in ((1, add_d_memory),
                                              (2, sub_d_memory)):
                            data = builder(size, source, 6, base, extension)
                            rows.append((len(image), kind, size, source, 6,
                                         base, extension, len(data)))
                            image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][8]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct RMW:Bus{unsigned count=0,reads=0,bytes=0,value=0,addresses[4]{},values[4]{};bool writes[4]{};
 void record(unsigned a,unsigned v,bool w){addresses[count]=a;values[count]=v;writes[count]=w;++count;}
 std::uint8_t read8(std::uint32_t a)override{record(a,value,false);++reads;return static_cast<std::uint8_t>(value);}
 std::uint16_t read16(std::uint32_t a)override{const unsigned v=bytes==4u&&reads==0u?value>>16u:value;
  record(a,v,false);++reads;return static_cast<std::uint16_t>(v);}
 void write8(std::uint32_t a,std::uint8_t v)override{record(a,v,true);}
 void write16(std::uint32_t a,std::uint16_t v)override{record(a,v,true);}};
int main(){const unsigned pairs[][2]={{0,0},{1,1},{0x7f,1},{0x80,1},
 {0xffff,1},{0x7fffffff,1},{0x80000000,0x80000000},{0xffffffff,1}};
 for(const auto& row:rows)for(const auto& pair:pairs){const unsigned bits=row[2]*8u;
  const unsigned mask=row[2]==4u?0xffffffffu:(1u<<bits)-1u,sign=1u<<(bits-1u);
  const unsigned destination=pair[0]&mask,sv=pair[1]&mask;
  CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);for(unsigned r=0;r<8u;++r){
   cpu.a[r]=0x2000u+r*0x100u;cpu.a_known[r]=true;cpu.d[r]=0x10u+r*4u;cpu.d_known[r]=0xffffffffu;}
  cpu.d[row[3]]=sv;if(row[2]!=1u&&row[4]==6u&&!(row[6]&0x8000u)&&
    ((row[6]>>12u)&7u)==row[3]&&(sv&1u))++cpu.a[row[5]];
  cpu.sr=0x271f;cpu.sr_known=0xffe0;const auto before=cpu;
  RMW bus;bus.bytes=row[2];bus.value=destination;if(!step(cpu,bus))return 1;
  unsigned address=0;if(row[4]==6u){const unsigned ext=row[6],index_reg=(ext>>12u)&7u;
   unsigned index=(ext&0x8000u)?before.a[index_reg]:before.d[index_reg];
   if(!(ext&0x0800u))index=(index&0x8000u)?(index&0xffffu)|0xffff0000u:index&0xffffu;
   const unsigned byte=ext&0xffu,disp=byte&0x80u?byte|0xffffff00u:byte;
   address=(before.a[row[5]]+index+disp)&0xffffffu;
  }else address=(row[4]==7u?row[6]:before.a[row[5]]+row[6])&0xffffffu;
  const bool subtract=row[1]!=1u;const unsigned result=subtract?
    (destination-sv)&mask:(destination+sv)&mask;const unsigned half=row[2]==4u?2u:1u;
  if(bus.count!=half*2u||bus.addresses[0]!=address||bus.writes[0]||!bus.writes[half]||
    bus.values[half]!=(row[2]==4u?result>>16u:result))return 2;
  const bool carry=subtract?destination<sv:static_cast<std::uint64_t>(destination)+sv>mask;
  const bool overflow=subtract?((destination^sv)&(destination^result)&sign)!=0u:
    (~(destination^sv)&(destination^result)&sign)!=0u;
  const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|(result==0u?4u:0u)|(overflow?2u:0u);
  if(cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu||cpu.d!=before.d||cpu.a!=before.a)return 3;
 }
 return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
