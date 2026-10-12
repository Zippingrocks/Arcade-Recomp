"""Intel ADDRL: ROM-free native tests using exact unbounded rational oracles."""
import random
import struct
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp
from test_i960_movr_native import COMMON, native
from test_i960_mulrl_native import exact_result, binary_value, extended_value, table


def addrl(a=0, b=1, d=8, *, af=True, bf=True, df=False):
    return (0x79000780 | a | (b << 14) | (d << 19) |
            (0x800 if af else 0) | (0x1000 if bf else 0) | (0x2000 if df else 0))


def sum_result(a, an, b, bn, fp, rounding):
    value = a + b
    negative = value < 0 if value else an if an == bn else rounding == 1
    return exact_result(value, negative, fp)


def binary_pairs():
    seeds = [0, 1 << 63, 0x3ff0000000000000, 0xbff0000000000000,
             0x3ff8000000000000, 0xbff8000000000000, 0x4000000000000000,
             0x0010000000000000, 0x0010000000000001, 0x7fefffffffffffff]
    pairs = [(a, b) for a in seeds for b in seeds]
    for gap in (0, 1, 2, 10, 11, 12, 52, 53, 54, 63, 64, 65, 66, 100, 2045):
        for fraction in (0, 1, (1 << 52) - 1):
            for sign in range(4):
                pairs.append(((sign & 1) << 63 | 2046 << 52 | fraction,
                              (sign >> 1) << 63 | (2046 - gap) << 52 | fraction))
    rng = random.Random(0x79f960)
    for _ in range(512):
        a = (rng.getrandbits(1) << 63) | (rng.randrange(1, 2047) << 52) | rng.getrandbits(52)
        b = a ^ (1 << 63) if rng.randrange(4) == 0 else (
            (rng.getrandbits(1) << 63) | (rng.randrange(1, 2047) << 52) | rng.getrandbits(52))
        pairs.append((a, b))
    return pairs


def binary_rows():
    rows = []
    for a, b in binary_pairs():
        av, bv = binary_value(a), binary_value(b)
        an, bn = bool(a >> 63), bool(b >> 63)
        ax, bx = exact_result(av, an, True), exact_result(bv, bn, True)
        for rounding in range(4):
            rows.append((a & 0xffffffff, a >> 32, *ax[1:], b & 0xffffffff, b >> 32, *bx[1:],
                         rounding, *sum_result(av, an, bv, bn, False, rounding),
                         *sum_result(av, an, bv, bn, True, rounding)))
    return rows


def extended_rows():
    half = 1 << 63
    seeds = []
    for exponent in (-16382, -1023, -1022, -1, 0, 1, 1023, 1024, 16383):
        for a, b in ((half, half), (half + 1, half), (half, half + 1),
                     ((1 << 64) - 1, half), ((1 << 64) - 1, (1 << 64) - 1)):
            for sign in range(4):
                seeds.append((a, exponent, bool(sign & 1), b, exponent, bool(sign & 2)))
    for gap in (1, 11, 52, 53, 63, 64, 65, 100, 32765):
        for a in (half, half + 1, (1 << 64) - 1):
            for b in (half, half + 1, (1 << 64) - 1):
                for sign in range(4):
                    seeds.append((a, 16383, bool(sign & 1), b, 16383 - gap, bool(sign & 2)))
    rng = random.Random(0x8079f)
    for _ in range(384):
        ae = rng.randrange(-16382, 16384)
        be = max(-16382, ae - rng.randrange(0, 70))
        seeds.append((half | rng.getrandbits(63), ae, bool(rng.getrandbits(1)),
                      half | rng.getrandbits(63), be, bool(rng.getrandbits(1))))
    # Exact gap64 subtraction: 1 - 2^-64 = (2^64-1)*2^-64.
    seeds.extend([(half, 0, False, half, -64, True), (half, -64, True, half, 0, False)])
    rows = []
    for a, ae, an, b, be, bn in seeds:
        av, bv = extended_value(a, ae, an), extended_value(b, be, bn)
        for rounding in range(4):
            rows.append((a & 0xffffffff, a >> 32, (ae + 16383) | (0x8000 if an else 0),
                         b & 0xffffffff, b >> 32, (be + 16383) | (0x8000 if bn else 0),
                         rounding, *sum_result(av, an, bv, bn, False, rounding),
                         *sum_result(av, an, bv, bn, True, rounding)))
    return rows


class ADDRLNativeTests(unittest.TestCase):
    def test_decode_modes_and_invalid_register_forms(self):
        self.assertEqual(decode(struct.pack("<I", addrl()), 0).operands, ("fp0", "fp1", "r8"))
        for mode in range(8):
            word = addrl(3 if mode & 1 else 30, 2 if mode & 2 else 28,
                         1 if mode & 4 else 26, af=bool(mode & 1), bf=bool(mode & 2), df=bool(mode & 4))
            self.assertEqual(decode(struct.pack("<I", word), 0).mnemonic, "addrl")
            self.assertNotIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)
        for word in (addrl() | 0x20, addrl() | 0x40, addrl(a=4), addrl(b=16),
                     addrl(a=22), addrl(d=4, df=True), addrl(a=31, af=False),
                     addrl(b=17, bf=False), addrl(d=31)):
            self.assertIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)

    def test_binary64_rational_matrix_all_eight_modes_and_rounding_controls(self):
        program = [addrl(0 if mode & 1 else 16, 1 if mode & 2 else 20, 2 if mode & 4 else 24,
                         af=bool(mode & 1), bf=bool(mode & 2), df=bool(mode & 4)) for mode in range(8)]
        native(program + [0xffffffff], "static const std::uint64_t rows[][19]={" + table(binary_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
    for(const auto& row:rows){for(unsigned mode=0;mode<8u;++mode){
        CPU cpu{};cpu.ip=mode*4u;
        if(!kb_establish_arithmetic_controls(cpu,(static_cast<std::uint32_t>(row[10])<<30u)|0x3f1f917fu))return 1;
        for(unsigned i=0;i<32u;++i){cpu.r[i]=0x12345600u+i;}
        cpu.r[16]=static_cast<std::uint32_t>(row[0]);cpu.r[17]=static_cast<std::uint32_t>(row[1]);
        cpu.r[20]=static_cast<std::uint32_t>(row[5]);cpu.r[21]=static_cast<std::uint32_t>(row[6]);
        cpu.fp[0]={static_cast<std::uint32_t>(row[2]),static_cast<std::uint32_t>(row[3]),static_cast<std::uint16_t>(row[4])};
        cpu.fp[1]={static_cast<std::uint32_t>(row[7]),static_cast<std::uint32_t>(row[8]),static_cast<std::uint16_t>(row[9])};
        cpu.fp_defined[0]=cpu.fp_defined[1]=true;
        CPU expected=cpu;const unsigned field=mode&4u?15u:11u;const bool ok=step(cpu,bus);
        if(row[field]==0u){
            expected.ip+=4u;
            if(mode&4u){expected.fp[2]={static_cast<std::uint32_t>(row[field+1u]),static_cast<std::uint32_t>(row[field+2u]),
                static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[2]=true;}
            else{expected.r[24]=static_cast<std::uint32_t>(row[field+1u]);expected.r[25]=static_cast<std::uint32_t>(row[field+2u]);}
            if(!ok||cpu.stop_code!=StopCode::none)return 2;
        }else{
            if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format)||cpu.stop_ip!=expected.ip)return 3;
        }
        if(!same_data(cpu,expected))return 4;
    }}
    return 0;
}
""")

    def test_extended_rational_precision_cancellation_range_and_gap64(self):
        native([addrl(), addrl(d=2, df=True), 0xffffffff],
               "static const std::uint64_t rows[][15]={" + table(extended_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
    for(const auto& row:rows){for(unsigned form=0;form<2u;++form){
        CPU cpu{};cpu.ip=form*4u;cpu.cc_defined=false;
        cpu.arithmetic_controls_other=static_cast<std::uint32_t>(row[6])<<30u;
        cpu.arithmetic_controls_other_defined_mask=0xc0000000u;
        cpu.fp[0]={static_cast<std::uint32_t>(row[0]),static_cast<std::uint32_t>(row[1]),static_cast<std::uint16_t>(row[2])};
        cpu.fp[1]={static_cast<std::uint32_t>(row[3]),static_cast<std::uint32_t>(row[4]),static_cast<std::uint16_t>(row[5])};
        cpu.fp_defined[0]=cpu.fp_defined[1]=true;cpu.r[8]=0x12345678u;cpu.r[9]=0xabcdef01u;
        CPU expected=cpu;const unsigned field=form?11u:7u;const bool ok=step(cpu,bus);
        if(row[field]==0u){
            expected.ip+=4u;
            if(form){expected.fp[2]={static_cast<std::uint32_t>(row[field+1u]),static_cast<std::uint32_t>(row[field+2u]),
                static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[2]=true;}
            else{expected.r[8]=static_cast<std::uint32_t>(row[field+1u]);expected.r[9]=static_cast<std::uint32_t>(row[field+2u]);}
            if(!ok)return 1;
        }else{
            if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format))return 2;
        }
        if(!same_data(cpu,expected))return 3;
    }}
    return 0;
}
""")

    def test_zero_sign_uses_only_necessary_known_rounding_bits(self):
        native([addrl(), addrl(d=2, df=True), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    for(unsigned known=0;known<4u;++known){for(unsigned stored=0;stored<4u;++stored){
        for(bool normal:{false,true}){for(unsigned form=0;form<2u;++form){
            bool positive=false,negative=false;
            for(unsigned concrete=0;concrete<4u;++concrete){
                if((concrete&known)==(stored&known)){
                    if(concrete==1u)negative=true;else positive=true;
                }
            }
            CPU cpu{};cpu.ip=form*4u;cpu.cc_defined=false;
            cpu.arithmetic_controls_other=(stored<<30u)|0x00190000u;
            cpu.arithmetic_controls_other_defined_mask=known<<30u;
            cpu.fp[0]={0u,normal?0x80000000u:0u,static_cast<std::uint16_t>(normal?16383u:0u)};
            cpu.fp[1]=cpu.fp[0];cpu.fp[1].high|=0x8000u;
            cpu.fp_defined[0]=cpu.fp_defined[1]=true;CPU expected=cpu;
            const bool ok=step(cpu,bus);
            if(positive&&negative){
                if(ok||cpu.stop_code!=StopCode::undefined_arithmetic_controls)return 1;
            }else{
                expected.ip+=4u;
                if(form){expected.fp[2]={0u,0u,static_cast<std::uint16_t>(negative?0x8000u:0u)};expected.fp_defined[2]=true;}
                else{expected.r[8]=0u;expected.r[9]=negative?0x80000000u:0u;}
                if(!ok)return 2;
            }
            if(!same_data(cpu,expected))return 3;
        }}
        // Same-sign zero does not consult unknown rounding controls.
        for(bool sign:{false,true}){
            CPU cpu{};cpu.arithmetic_controls_other=stored<<30u;
            cpu.arithmetic_controls_other_defined_mask=known<<30u;
            cpu.fp[0]=cpu.fp[1]={0u,0u,static_cast<std::uint16_t>(sign?0x8000u:0u)};
            cpu.fp_defined[0]=cpu.fp_defined[1]=true;CPU expected=cpu;
            expected.ip=4u;expected.r[9]=sign?0x80000000u:0u;
            if(!step(cpu,bus)||!same_data(cpu,expected))return 4;
        }
    }}
    return 0;
}
""")

    def test_aliases_register_limits_and_unknown_controls_on_nonzero(self):
        native([addrl(), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    CPU initial{};initial.fp[0]=initial.fp[1]={0u,0xc0000000u,16383u};
    initial.fp_defined[0]=initial.fp_defined[1]=true;
    if(!step(initial,bus)||initial.r[8]!=0u||initial.r[9]!=0x40080000u)return 1;
    for(unsigned a=0;a<4u;++a){for(unsigned b=0;b<4u;++b){for(unsigned dst=0;dst<4u;++dst){
        CPU cpu{};cpu.cc_defined=false;cpu.fp[a]=cpu.fp[b]={0u,0xc0000000u,16383u};
        cpu.fp_defined[a]=cpu.fp_defined[b]=true;CPU expected=cpu;
        expected.fp[dst]={0u,0xc0000000u,16384u};expected.fp_defined[dst]=true;
        if(!add_long_real_exact(cpu,a,true,b,true,dst,true)||!same_data(cpu,expected))return 2;
    }}}
    for(unsigned a=0;a<32u;a+=2u){for(unsigned b=0;b<32u;b+=2u){for(unsigned dst=0;dst<32u;dst+=2u){
        CPU cpu{};cpu.r[a]=cpu.r[b]=0u;cpu.r[a+1u]=cpu.r[b+1u]=0x3ff80000u;
        CPU expected=cpu;expected.r[dst]=0u;expected.r[dst+1u]=0x40080000u;
        if(!add_long_real_exact(cpu,a,false,b,false,dst,false)||!same_data(cpu,expected))return 3;
    }}}
    return 0;
}
""")

    def test_zero_addend_still_checks_destination_range_and_precision(self):
        native([addrl(), addrl(d=2, df=True), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    const ExtendedReal values[]={{0u,0x80000000u,16383u},{1u,0x80000000u,16383u},
        {0u,0x80000000u,15360u},{0u,0x80000000u,17407u}};
    for(unsigned index=0;index<4u;++index){for(unsigned side=0;side<2u;++side){
        for(unsigned form=0;form<2u;++form){for(bool sign:{false,true}){
            CPU cpu{};cpu.ip=form*4u;cpu.cc_defined=false;
            cpu.fp[side]=values[index];if(sign)cpu.fp[side].high|=0x8000u;
            cpu.fp[1u-side]={0u,0u,0x8000u};cpu.fp_defined[0]=cpu.fp_defined[1]=true;
            CPU expected=cpu;const bool ok=step(cpu,bus);
            if(form||index==0u){
                expected.ip+=4u;
                if(form){expected.fp[2]=cpu.fp[side];expected.fp_defined[2]=true;}
                else{expected.r[8]=0u;expected.r[9]=sign?0xbff00000u:0x3ff00000u;}
                if(!ok)return 1;
            }else{
                if(ok||cpu.stop_code!=(index==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format))return 2;
            }
            if(!same_data(cpu,expected))return 3;
        }}
    }}
    return 0;
}
""")

    def test_unsupported_values_indices_reset_and_pending_fault_are_atomic(self):
        native([addrl(), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    const ExtendedReal bad[]={{1u,0u,0u},{0u,0x80000000u,0u},{0u,0u,16383u},
        {0u,0x80000000u,0x7fffu},{1u,0x80000000u,0x7fffu},{0u,0xc0000000u,0xffffu}};
    for(auto value:bad){for(unsigned side=0;side<2u;++side){for(bool defined:{false,true}){
        CPU cpu{};cpu.fp[side]=value;cpu.fp_defined[0]=cpu.fp_defined[1]=true;
        cpu.fp_defined[side]=defined;cpu.r[8]=0x12345678u;cpu.r[9]=0xabcdef01u;
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=(defined?StopCode::unsupported_floating_format:
           StopCode::undefined_floating_point_register)||!same_data(cpu,before))return 1;
    }}}
    for(auto bits:{1ull,0x8000000000000001ull,0x7ff0000000000000ull,0x7ff8000000000001ull}){
        CPU cpu{};cpu.r[30]=static_cast<std::uint32_t>(bits);cpu.r[31]=static_cast<std::uint32_t>(bits>>32u);
        cpu.fp_defined[1]=true;const CPU before=cpu;
        if(add_long_real_exact(cpu,30u,false,1u,true,0u,true)||cpu.stop_code!=StopCode::unsupported_floating_format||!same_data(cpu,before))return 2;
    }
    for(auto index:{4u,31u,32u,0xffffffffu}){for(bool fp:{false,true}){
        if(fp?index<4u:(index<32u&&(index&1u)==0u))continue;
        for(unsigned slot=0;slot<3u;++slot){
            CPU cpu{};cpu.fp_defined[0]=cpu.fp_defined[1]=true;const CPU before=cpu;
            if(add_long_real_exact(cpu,slot==0u?index:0u,slot==0u?fp:true,
               slot==1u?index:1u,slot==1u?fp:true,slot==2u?index:2u,slot==2u?fp:true)||
               cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 3;
        }
    }}
    CPU cpu{};cpu.pending_integer_overflow={true,0x80u,0x84u};const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::integer_overflow_pending||cpu.stop_ip!=0x80u||
       !cpu.pending_integer_overflow.pending||!same_data(cpu,before))return 4;
    cpu={};cpu.fp_defined[0]=cpu.fp_defined[1]=true;
    if(!frame_init(cpu,0x100u,0u))return 5;
    const CPU reset=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register||!same_data(cpu,reset))return 6;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
