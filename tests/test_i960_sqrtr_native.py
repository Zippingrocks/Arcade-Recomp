"""Intel KB SQRTR synthetic native tests with independent rational/isqrt oracles."""
from fractions import Fraction
import math
import random
import struct
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp
from test_i960_movr_native import COMMON, native


def sqrtr(src=22, dst=20, *, sf=False, df=False):
    return 0x68001400 | src | (dst << 19) | (0x800 if sf else 0) | (0x2000 if df else 0)


def power2(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def encode(value, negative, fp):
    """Encode an exact rational; 1 means inexact, 2 unsupported normal range."""
    if not value:
        return (0, 0, 0, 0x8000 if negative else 0) if fp else (0, 0x80000000 if negative else 0, 0, 0)
    magnitude = abs(value)
    exponent = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    if magnitude < power2(exponent):
        exponent -= 1
    minimum, maximum, precision = (-16382, 16383, 64) if fp else (-126, 127, 24)
    if not minimum <= exponent <= maximum:
        return 2, 0, 0, 0
    scaled = magnitude / power2(exponent - precision + 1)
    if scaled.denominator != 1:
        return 1, 0, 0, 0
    significand = scaled.numerator
    if fp:
        return 0, significand & 0xffffffff, significand >> 32, (exponent + 16383) | (0x8000 if negative else 0)
    bits = (int(negative) << 31) | ((exponent + 127) << 23) | (significand - (1 << 23))
    return 0, bits, 0, 0


def sqrt_result(value, negative, fp):
    if value < 0:
        return 2, 0, 0, 0
    # Python's unbounded integer sqrt applied separately to reduced rational
    # numerator/denominator, not the runtime's odd-significand decomposition.
    numerator = math.isqrt(value.numerator)
    denominator = math.isqrt(value.denominator)
    if numerator * numerator != value.numerator or denominator * denominator != value.denominator:
        return 1, 0, 0, 0
    return encode(Fraction(numerator, denominator), negative, fp)


def binary_rows():
    values = [0, 0x80000000]
    values += [(exponent << 23) | fraction for exponent in range(1, 255)
               for fraction in (0, 1, 0x100000, 0x7fffff)]
    # Supply many non-power-of-two exact roots across the real32 range.
    for root in (3, 5, 7, 31, 127, 511, 1023, 2047, 4095):
        for exponent in (-120, -80, -20, -2, 0, 20, 80, 100):
            result = encode(root * root * power2(exponent), False, False)
            if result[0] == 0:
                values.append(result[1])
    rng = random.Random(0x688960)
    values += [(rng.randrange(1, 255) << 23) | rng.getrandbits(23) for _ in range(512)]
    values += [bits | 0x80000000 for bits in values[2:130]]
    rows = []
    for bits in values:
        value = Fraction(struct.unpack("<f", struct.pack("<I", bits))[0])
        negative = bool(bits >> 31)
        source = encode(value, negative, True)
        assert source[0] == 0
        rows.append((bits, *source[1:], *sqrt_result(value, negative, False), *sqrt_result(value, negative, True)))
    return rows


def extended_rows():
    seeds = []
    for root in (1, 3, 5, 4095, (1 << 23) - 1, (1 << 23) + 1,
                 (1 << 24) - 1, (1 << 24) + 1, (1 << 31) - 1,
                 (1 << 31) + 1, (1 << 32) - 1):
        for exponent in (-8191, -128, -127, -126, -1, 0, 1, 126, 127, 128, 8190, 8191):
            value = Fraction(root * root) * power2(2 * (exponent - root.bit_length() + 1))
            if encode(value, False, True)[0] == 0:
                seeds.append(value)
    rng = random.Random(0x80688)
    for _ in range(256):
        seeds.append(Fraction((1 << 63) | rng.getrandbits(63)) * power2(rng.randrange(-16382, 16384) - 63))
    seeds += [power2(e) for e in (-16382, -16381, 16382, 16383)]
    rows = []
    for value in seeds:
        source = encode(value, False, True)
        assert source[0] == 0
        rows.append((*source[1:], *sqrt_result(value, False, False), *sqrt_result(value, False, True)))
    return rows


def table(rows):
    return ",\n".join("{" + ",".join(f"{x}ull" for x in row) + "}" for row in rows)


class SQRTRNativeTests(unittest.TestCase):
    def test_decode_all_register_forms_and_refuse_invalid_encodings(self):
        for src, dst, sf, df, operands in (
            (22, 20, False, False, ("g6", "g4")),
            (31, 3, False, True, ("g15", "fp3")),
            (2, 31, True, False, ("fp2", "g15")),
            (3, 1, True, True, ("fp3", "fp1")),
        ):
            word = sqrtr(src, dst, sf=sf, df=df)
            ins = decode(struct.pack("<I", word), 0)
            self.assertEqual((ins.mnemonic, ins.operands), ("sqrtr", operands))
            self.assertNotIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)
        for word in (sqrtr() | 0x20, sqrtr() | 0x40, sqrtr() | (1 << 14),
                     sqrtr() & ~0x1000, sqrtr(4, sf=True), sqrtr(16, sf=True),
                     sqrtr(22, sf=True), sqrtr(dst=4, df=True), sqrtr() | 0x1000000):
            self.assertIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)

    def test_integer_square_root_against_unbounded_oracle(self):
        values = list(range(1024)) + [1 << 63, (1 << 64) - 1]
        roots = [1, 2, 3, (1 << 16) - 1, 1 << 16, (1 << 31) - 1, 1 << 31, (1 << 32) - 1]
        rng = random.Random(0x64688)
        roots += [rng.getrandbits(32) for _ in range(512)]
        values += [root * root + delta for root in roots for delta in (-1, 0, 1)]
        values += [rng.getrandbits(64) for _ in range(512)]
        rows = [(value, math.isqrt(value)) for value in values]
        native([sqrtr(), 0xffffffff], "static const std::uint64_t rows[][2]={" + table(rows) + "};\n" + r"""
using namespace arcaderecomp_generated;
int main(){
    for(const auto& row:rows){if(sqrt_unsigned_64_floor(row[0])!=row[1])return 1;}
    CPU cpu{};Bus bus{};cpu.r[22]=0x40800000u;
    if(!step(cpu,bus)||cpu.ip!=4u||cpu.r[20]!=0x40000000u)return 2;
    return 0;
}
""")

    def test_binary32_rational_matrix_all_register_forms_and_ac_profiles(self):
        program = [sqrtr(0 if form & 1 else 22, 1 if form & 2 else 20,
                         sf=bool(form & 1), df=bool(form & 2)) for form in range(4)]
        native(program + [0xffffffff], "static const std::uint64_t rows[][12]={" + table(binary_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
    for(const auto& row:rows){for(unsigned form=0;form<4u;++form){
        for(auto ac:{0u,0x401f917fu,0x801f917fu,0xff1f917fu}){
            CPU cpu{};cpu.ip=form*4u;
            if(!kb_establish_arithmetic_controls(cpu,ac))return 1;
            for(unsigned i=0;i<32u;++i){cpu.r[i]=0x12345600u+i;}
            cpu.r[22]=static_cast<std::uint32_t>(row[0]);
            cpu.fp[0]={static_cast<std::uint32_t>(row[1]),static_cast<std::uint32_t>(row[2]),static_cast<std::uint16_t>(row[3])};
            cpu.fp_defined[0]=true;cpu.fp[1]={12u,34u,56u};cpu.fp_defined[1]=bool(form&1u);
            CPU expected=cpu;const unsigned field=form&2u?8u:4u;
            const bool ok=step(cpu,bus);
            if(row[field]==0u){
                expected.ip+=4u;
                if(form&2u){expected.fp[1]={static_cast<std::uint32_t>(row[field+1u]),
                    static_cast<std::uint32_t>(row[field+2u]),static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[1]=true;}
                else{expected.r[20]=static_cast<std::uint32_t>(row[field+1u]);}
                if(!ok||cpu.stop_code!=StopCode::none)return 2;
            }else{
                if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format)||cpu.stop_ip!=expected.ip)return 3;
            }
            if(!same_data(cpu,expected))return 4;
        }
    }}
    return 0;
}
""")

    def test_extended_precision_range_boundaries_and_unknown_ac(self):
        native([sqrtr(0, 20, sf=True), sqrtr(0, 1, sf=True, df=True), 0xffffffff],
               "static const std::uint64_t rows[][11]={" + table(extended_rows()) + "};\n" + COMMON + r"""
int main(){Bus bus{};
    for(const auto& row:rows){for(unsigned form=0;form<2u;++form){
        CPU cpu{};cpu.ip=form*4u;cpu.cc_defined=false;
        cpu.arithmetic_controls_other=0x80100000u;cpu.arithmetic_controls_other_defined_mask=0x80100000u;
        cpu.fp[0]={static_cast<std::uint32_t>(row[0]),static_cast<std::uint32_t>(row[1]),static_cast<std::uint16_t>(row[2])};
        cpu.fp_defined[0]=true;cpu.r[20]=0x12345678u;
        CPU expected=cpu;const unsigned field=form?7u:3u;const bool ok=step(cpu,bus);
        if(row[field]==0u){
            expected.ip+=4u;
            if(form){expected.fp[1]={static_cast<std::uint32_t>(row[field+1u]),static_cast<std::uint32_t>(row[field+2u]),
                static_cast<std::uint16_t>(row[field+3u])};expected.fp_defined[1]=true;}
            else{expected.r[20]=static_cast<std::uint32_t>(row[field+1u]);}
            if(!ok)return 1;
        }else{
            if(ok||cpu.stop_code!=(row[field]==1u?StopCode::unsupported_floating_rounding:StopCode::unsupported_floating_format))return 2;
        }
        if(!same_data(cpu,expected))return 3;
    }}
    return 0;
}
""")

    def test_aliases_signed_zeros_and_register_boundaries(self):
        native([sqrtr(), 0xffffffff], COMMON + r"""
int main(){
    CPU initial{};Bus bus{};initial.r[22]=0x41100000u;
    if(!step(initial,bus)||initial.ip!=4u||initial.r[20]!=0x40400000u)return 1;
    for(unsigned src=0;src<32u;++src){for(unsigned dst=0;dst<32u;++dst){
        CPU cpu{};cpu.r[src]=0x40100000u;CPU expected=cpu;expected.r[dst]=0x3fc00000u;
        if(!square_root_real_exact(cpu,src,false,dst,false)||!same_data(cpu,expected))return 2;
    }}
    for(unsigned src=0;src<4u;++src){for(unsigned dst=0;dst<4u;++dst){
        CPU cpu{};cpu.fp[src]={0u,0x90000000u,16384u};cpu.fp_defined[src]=true;
        CPU expected=cpu;expected.fp[dst]={0u,0xc0000000u,16383u};expected.fp_defined[dst]=true;
        if(!square_root_real_exact(cpu,src,true,dst,true)||!same_data(cpu,expected))return 3;
    }}
    for(bool negative:{false,true}){for(bool sf:{false,true}){for(bool df:{false,true}){
        CPU cpu{};cpu.r[31]=negative?0x80000000u:0u;
        cpu.fp[3]={0u,0u,static_cast<std::uint16_t>(negative?0x8000u:0u)};cpu.fp_defined[3]=true;
        CPU expected=cpu;
        if(df){expected.fp[1]=cpu.fp[3];expected.fp_defined[1]=true;}
        else{expected.r[30]=cpu.r[31];}
        if(!square_root_real_exact(cpu,sf?3u:31u,sf,df?1u:30u,df)||!same_data(cpu,expected))return 4;
    }}}
    return 0;
}
""")

    def test_special_undefined_invalid_and_pending_fault_refusal(self):
        native([sqrtr(), sqrtr(0, 1, sf=True, df=True), 0xffffffff], COMMON + r"""
int main(){Bus bus{};
    for(auto bits:{1u,0x007fffffu,0x80000001u,0x7f800000u,0xff800000u,0x7fc00000u,0x7f800001u,0xbf800000u}){
        CPU cpu{};cpu.r[22]=bits;cpu.r[20]=0x12345678u;const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_format||!same_data(cpu,before))return 1;
    }
    const ExtendedReal bad[]={{1u,0u,0u},{0u,0x80000000u,0u},{0u,0u,16383u},
        {0u,0x80000000u,0x7fffu},{1u,0x80000000u,0x7fffu},{0u,0xc0000000u,0xffffu},
        {0u,0x80000000u,0xbfffu}};
    for(auto value:bad){for(bool defined:{false,true}){
        CPU cpu{};cpu.ip=4u;cpu.fp[0]=value;cpu.fp_defined[0]=defined;
        cpu.fp[1]={12u,34u,56u};cpu.fp_defined[1]=true;const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=(defined?StopCode::unsupported_floating_format:StopCode::undefined_floating_point_register)||!same_data(cpu,before))return 2;
    }}
    for(auto index:{4u,31u,32u,0xffffffffu}){for(bool fp:{false,true}){
        if(index<(fp?4u:32u))continue;
        CPU cpu{};cpu.r[22]=0x40800000u;CPU before=cpu;
        if(square_root_real_exact(cpu,index,fp,20u,false)||cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 3;
        cpu=before;
        if(square_root_real_exact(cpu,22u,false,index,fp)||cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 4;
    }}
    CPU cpu{};cpu.r[22]=0x40800000u;cpu.pending_integer_overflow={true,0x80u,0x84u};
    const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::integer_overflow_pending||cpu.stop_ip!=0x80u||
       !cpu.pending_integer_overflow.pending||!same_data(cpu,before))return 5;
    cpu={};cpu.fp_defined[0]=true;
    if(!frame_init(cpu,0x100u,4u))return 6;
    const CPU reset=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register||!same_data(cpu,reset))return 7;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
