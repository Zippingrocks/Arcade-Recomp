"""Intel KB MULRL synthetic native tests with unbounded/rational oracles."""
from fractions import Fraction
import random
import struct
import unittest
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp
from test_i960_movr_native import COMMON, native


def mulrl(a=0, b=2, d=8, *, af=True, bf=True, df=False):
    return (0x79000600 | a | (b << 14) | (d << 19) |
            (0x800 if af else 0) | (0x1000 if bf else 0) | (0x2000 if df else 0))


def power2(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def exact_result(value, negative, fp):
    """Classify/encode a mathematical rational in the destination precision."""
    if not value:
        return (0, 0, 0, 0x8000 if negative else 0) if fp else (0, 0, 0x80000000 if negative else 0, 0)
    magnitude = abs(value)
    exponent = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    if magnitude < power2(exponent):
        exponent -= 1
    minimum, maximum, precision, bias = (-16382, 16383, 64, 16383) if fp else (-1022, 1023, 53, 1023)
    if not minimum <= exponent <= maximum:
        return 2, 0, 0, 0
    scaled = magnitude / power2(exponent - precision + 1)
    if scaled.denominator != 1:
        return 1, 0, 0, 0
    significand = scaled.numerator
    if fp:
        return 0, significand & 0xffffffff, significand >> 32, (exponent + bias) | (0x8000 if negative else 0)
    bits = (int(negative) << 63) | ((exponent + bias) << 52) | (significand - (1 << 52))
    return 0, bits & 0xffffffff, bits >> 32, 0


def binary_value(bits):
    return Fraction(struct.unpack("<d", struct.pack("<Q", bits))[0])


def binary_rows():
    pairs = [(a, b) for a in (0, 1 << 63) for b in (0, 1 << 63, 0x3ff0000000000000, 0xbff0000000000000)]
    for exponent in (1, 2, 511, 1022, 1023, 1024, 1535, 2045, 2046):
        for fraction in (0, 1, (1 << 52) - 1):
            for sign in range(2):
                a = sign << 63 | exponent << 52 | fraction
                for b in (0x3ff0000000000000, 0xbff0000000000000, 0x4000000000000000,
                          0x3fe0000000000000, 0x3ff8000000000000, 0xbff8000000000000):
                    pairs.append((a, b))
    rng = random.Random(0x79c960)
    for _ in range(512):
        pairs.append(tuple((rng.getrandbits(1) << 63) | (rng.randrange(1, 2047) << 52) |
                           rng.getrandbits(52) for _ in range(2)))
    rows = []
    for a, b in pairs:
        av, bv = binary_value(a), binary_value(b)
        ax, bx = exact_result(av, bool(a >> 63), True), exact_result(bv, bool(b >> 63), True)
        assert ax[0] == bx[0] == 0
        negative = bool((a ^ b) >> 63)
        rows.append((a & 0xffffffff, a >> 32, *ax[1:], b & 0xffffffff, b >> 32, *bx[1:],
                     *exact_result(av * bv, negative, False), *exact_result(av * bv, negative, True)))
    return rows


def extended_value(significand, exponent, negative=False):
    return (-1 if negative else 1) * Fraction(significand, 1 << 63) * power2(exponent)


def extended_rows():
    half = 1 << 63
    seeds = []
    # Preserve lowest extended bits, exercise both normalization branches,
    # and cross binary64/extended range and precision boundaries.
    for exponent in (-16382, -1023, -1022, -1, 0, 1, 1023, 1024, 16383):
        for significand in (half, half + 1, half | (1 << 62), (1 << 64) - 1):
            for second in (half, half + 1, half | (1 << 62)):
                for b_exponent in (-1, 0, 1):
                    seeds.append((significand, exponent, second, b_exponent))
    rng = random.Random(0x8079c)
    for _ in range(384):
        a = half | rng.getrandbits(63)
        # Some random products are exact in extended80; others require >64 bits.
        b = half if rng.randrange(3) == 0 else half | rng.getrandbits(63)
        seeds.append((a, rng.randrange(-16382, 16384), b, rng.randrange(-32, 33)))
    rows = []
    for i, (a, ae, b, be) in enumerate(seeds):
        an, bn = bool(i & 1), bool(i & 2)
        av, bv = extended_value(a, ae, an), extended_value(b, be, bn)
        rows.append((a & 0xffffffff, a >> 32, (ae + 16383) | (0x8000 if an else 0),
                     b & 0xffffffff, b >> 32, (be + 16383) | (0x8000 if bn else 0),
                     *exact_result(av * bv, an != bn, False), *exact_result(av * bv, an != bn, True)))
    return rows


def table(rows):
    return ",\n".join("{" + ",".join(f"{x}ull" for x in row) + "}" for row in rows)


class MULRLNativeTests(unittest.TestCase):
    def test_decode_mixed_formats_and_refuse_invalid_modes(self):
        self.assertEqual(decode(struct.pack("<I", mulrl()), 0).operands, ("fp0", "fp2", "r8"))
        self.assertEqual(decode(struct.pack("<I", mulrl(16, 20, 3, af=False, bf=False, df=True)), 0).operands,
                         ("g0", "g4", "fp3"))
        for word in (mulrl() | 0x20, mulrl() | 0x40, mulrl(a=4), mulrl(b=16),
                     mulrl(a=22), mulrl(d=4, df=True), mulrl(d=31),
                     mulrl(a=17, af=False), mulrl(b=21, bf=False)):
            self.assertIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)

    def test_portable_wide_product_against_unbounded_integer_oracle(self):
        values = [0, 1, 2, (1 << 32) - 1, 1 << 32, (1 << 32) + 1,
                  (1 << 63) - 1, 1 << 63, (1 << 63) + 1, (1 << 64) - 1,
                  0xaaaaaaaaaaaaaaaa, 0x5555555555555555]
        pairs = [(a, b) for a in values for b in values]
        rng = random.Random(0x12879c)
        pairs += [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(2048)]
        rows = [(a, b, (a * b) & ((1 << 64) - 1), (a * b) >> 64) for a, b in pairs]
        native([mulrl(), 0xffffffff], "static const std::uint64_t rows[][4]={" + table(rows) + "};\n" + r"""
using namespace arcaderecomp_generated;
int main(){
    for(const auto& row:rows){
        const auto p=multiply_unsigned_64_wide(row[0],row[1]);
        if(p.low!=row[2]||p.high!=row[3])return 1;
    }
    CPU cpu{};Bus bus{};cpu.fp_defined[0]=cpu.fp_defined[2]=true;
    if(!step(cpu,bus)||cpu.ip!=4u||cpu.r[8]!=0u||cpu.r[9]!=0u)return 2;
    return 0;
}
""")

    def test_binary64_matrix_all_eight_register_modes_and_ac_profiles(self):
        program = [mulrl(0 if k & 1 else 16, 2 if k & 2 else 20, 1 if k & 4 else 24,
                         af=bool(k & 1), bf=bool(k & 2), df=bool(k & 4)) for k in range(8)]
        native(program + [0xffffffff], "static const std::uint64_t rows[][18]={" + table(binary_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
for(const auto& row:rows){for(unsigned mode=0;mode<8u;++mode){
for(auto ac:{0u,0x401f917fu,0x801f917fu,0xff1f917fu}){
    CPU cpu{};cpu.ip=mode*4u;if(!kb_establish_arithmetic_controls(cpu,ac))return 1;
    for(unsigned i=0;i<32u;++i)cpu.r[i]=0x12345600u+i;
    cpu.r[16]=static_cast<std::uint32_t>(row[0]);cpu.r[17]=static_cast<std::uint32_t>(row[1]);
    cpu.r[20]=static_cast<std::uint32_t>(row[5]);cpu.r[21]=static_cast<std::uint32_t>(row[6]);
    cpu.fp[0]={static_cast<std::uint32_t>(row[2]),static_cast<std::uint32_t>(row[3]),static_cast<std::uint16_t>(row[4])};
    cpu.fp[2]={static_cast<std::uint32_t>(row[7]),static_cast<std::uint32_t>(row[8]),static_cast<std::uint16_t>(row[9])};
    cpu.fp_defined[0]=cpu.fp_defined[2]=true;
    cpu.fp[1]={12u,34u,56u};cpu.fp_defined[1]=bool(mode&1u);
    CPU expected=cpu;const unsigned field=mode&4u?14u:10u;
    const bool ok=step(cpu,bus);
    if(row[field]==0u){
        expected.ip+=4u;
        if(mode&4u){expected.fp[1]={static_cast<std::uint32_t>(row[field+1u]),
            static_cast<std::uint32_t>(row[field+2u]),static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[1]=true;}
        else{expected.r[24]=static_cast<std::uint32_t>(row[field+1u]);expected.r[25]=static_cast<std::uint32_t>(row[field+2u]);}
        if(!ok||cpu.stop_code!=StopCode::none)return 2;
    }else if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format))return 3;
    if(!same_data(cpu,expected))return 4;
}}}
return 0;}
""")

    def test_full_extended_precision_and_destination_range_boundaries(self):
        native([mulrl(), mulrl(d=1, df=True), 0xffffffff],
               "static const std::uint64_t rows[][14]={" + table(extended_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
for(const auto& row:rows){for(unsigned form=0;form<2u;++form){
    CPU cpu{};cpu.ip=form*4u;cpu.cc_defined=false;
    cpu.arithmetic_controls_other=0x80100000u;cpu.arithmetic_controls_other_defined_mask=0x80100000u;
    cpu.fp[0]={static_cast<std::uint32_t>(row[0]),static_cast<std::uint32_t>(row[1]),static_cast<std::uint16_t>(row[2])};
    cpu.fp[2]={static_cast<std::uint32_t>(row[3]),static_cast<std::uint32_t>(row[4]),static_cast<std::uint16_t>(row[5])};
    cpu.fp_defined[0]=cpu.fp_defined[2]=true;cpu.r[8]=0x12345678u;cpu.r[9]=0xabcdef01u;
    CPU expected=cpu;const unsigned field=form==0u?6u:10u;
    const bool ok=step(cpu,bus);
    if(row[field]==0u){expected.ip+=4u;
        if(form){expected.fp[1]={static_cast<std::uint32_t>(row[field+1u]),static_cast<std::uint32_t>(row[field+2u]),
            static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[1]=true;}
        else{expected.r[8]=static_cast<std::uint32_t>(row[field+1u]);expected.r[9]=static_cast<std::uint32_t>(row[field+2u]);}
        if(!ok)return 1;
    }else if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format))return 2;
    if(!same_data(cpu,expected))return 3;
}}
return 0;}
""")

    def test_aliases_zero_signs_and_highest_register_boundaries(self):
        native([mulrl(), 0xffffffff], COMMON + r"""
int main(){
    CPU initial{};Bus bus{};initial.fp_defined[0]=initial.fp_defined[2]=true;
    if(!step(initial,bus)||initial.ip!=4u||initial.r[8]!=0u||initial.r[9]!=0u)return 5;
    for(unsigned first=0;first<4u;++first)for(unsigned second=0;second<4u;++second)
    for(unsigned dst=0;dst<4u;++dst){
        CPU cpu{};cpu.fp[first]={0u,0xc0000000u,16383u};cpu.fp_defined[first]=true;
        cpu.fp[second]={0u,0xc0000000u,16383u};cpu.fp_defined[second]=true;
        CPU expected=cpu;expected.fp[dst]={0u,0x90000000u,16384u};expected.fp_defined[dst]=true;
        if(!multiply_long_real_exact(cpu,first,true,second,true,dst,true)||!same_data(cpu,expected))return 1;
    }
    for(unsigned first=0;first<32u;first+=2u)for(unsigned second=0;second<32u;second+=2u)
    for(unsigned dst=0;dst<32u;dst+=2u){
        CPU cpu{};cpu.r[first]=0u;cpu.r[first+1u]=0x3ff80000u;
        cpu.r[second]=0u;cpu.r[second+1u]=0x3ff80000u;
        CPU expected=cpu;expected.r[dst]=0u;expected.r[dst+1u]=0x40020000u;
        if(!multiply_long_real_exact(cpu,first,false,second,false,dst,false)||!same_data(cpu,expected))return 2;
    }
    for(unsigned sign=0;sign<4u;++sign){
        CPU cpu{};cpu.fp[0]={0u,0u,static_cast<std::uint16_t>((sign&1u)?0x8000u:0u)};
        cpu.fp[2]={0u,0x80000000u,static_cast<std::uint16_t>(1u|((sign&2u)?0x8000u:0u))};
        cpu.fp_defined[0]=cpu.fp_defined[2]=true;
        if(!multiply_long_real_exact(cpu,0u,true,2u,true,1u,true)||cpu.fp[1].low||cpu.fp[1].middle||
           cpu.fp[1].high!=(((sign&1u)!=((sign>>1u)&1u))?0x8000u:0u))return 3;
    }
    // A full-precision FP value (not representable in binary64) multiplied
    // by a GPR power of two stays exact in FP, in both source orders.
    for(bool reverse:{false,true}){
        CPU cpu{};cpu.fp[0]={1u,0x80000000u,16383u};cpu.fp_defined[0]=true;
        cpu.r[30]=0u;cpu.r[31]=0x40000000u;
        CPU expected=cpu;expected.fp[0].high=16384u;
        if(!multiply_long_real_exact(cpu,reverse?30u:0u,!reverse,
           reverse?0u:30u,reverse,0u,true)||!same_data(cpu,expected))return 4;
    }
    return 0;
}
""")

    def test_special_undefined_and_invalid_operands_preserve_state(self):
        native([mulrl(), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    const ExtendedReal bad[]={{1u,0u,0u},{0u,0x80000000u,0u},{0u,0u,16383u},
        {0u,0x80000000u,0x7fffu},{1u,0x80000000u,0x7fffu},{0u,0xc0000000u,0xffffu}};
    for(auto value:bad)for(unsigned side=0;side<2u;++side)for(bool defined:{false,true}){
        CPU cpu{};cpu.fp[side*2u]=value;cpu.fp_defined[0]=cpu.fp_defined[2]=true;
        // Other source is explicitly known zero; it must not hide a bad operand.
        cpu.fp_defined[side*2u]=defined;cpu.r[8]=0x12345678u;cpu.r[9]=0xabcdef01u;
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=(defined?StopCode::unsupported_floating_format:
           StopCode::undefined_floating_point_register)||!same_data(cpu,before))return 1;
    }
    for(auto bits:{1ull,0x8000000000000001ull,0x7ff0000000000000ull,0x7ff8000000000001ull}){
        CPU cpu{};cpu.r[16]=static_cast<std::uint32_t>(bits);cpu.r[17]=static_cast<std::uint32_t>(bits>>32u);
        cpu.fp_defined[2]=true;const CPU before=cpu;
        if(multiply_long_real_exact(cpu,16u,false,2u,true,1u,true)||
           cpu.stop_code!=StopCode::unsupported_floating_format||!same_data(cpu,before))return 2;
    }
    for(auto index:{4u,31u,32u,0xffffffffu})for(bool fp:{false,true}){
        if(fp?index<4u:(index<32u&&(index&1u)==0u))continue;
        for(unsigned slot=0;slot<3u;++slot){
            CPU cpu{};cpu.fp_defined[0]=cpu.fp_defined[2]=true;CPU before=cpu;
            if(multiply_long_real_exact(cpu,slot==0u?index:0u,slot==0u?fp:true,
               slot==1u?index:2u,slot==1u?fp:true,slot==2u?index:1u,slot==2u?fp:true)||
               cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 3;
        }
    }
    CPU cpu{};cpu.pending_integer_overflow={true,0x80u,0x84u};const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::integer_overflow_pending||cpu.stop_ip!=0x80u||
       !same_data(cpu,before))return 4;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
