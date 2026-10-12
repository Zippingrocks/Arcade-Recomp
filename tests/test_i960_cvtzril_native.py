"""Synthetic Intel CVTZRIL exact signed-64 conversion and atomic stops."""
from fractions import Fraction
import random
import struct
import unittest
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp
from test_i960_movr_native import COMMON, native


def cvtzril(src=0, dst=20, *, source_fp=True):
    # Intel B-1/B-2: M1=1 selects FP source; bits5/6 stay zero.
    return 0x6c001180 | src | (dst << 19) | (0x800 if source_fp else 0)


def integer_extended(value):
    magnitude = abs(value)
    if not magnitude:
        return 0, 0, 0
    exponent = magnitude.bit_length() - 1
    significand = magnitude << (63 - exponent)
    return significand & 0xffffffff, significand >> 32, (16383 + exponent) | (0x8000 if value < 0 else 0)


def fp_rows():
    values = [0, 1, -1, (1 << 63) - 1, -(1 << 63), 1 << 63,
              -(1 << 63) - 1, (1 << 64) - 1, -((1 << 64) - 1)]
    for bit in range(64):
        values += [1 << bit, -(1 << bit), (1 << bit) - 1, 1 - (1 << bit)]
    rng = random.Random(0x6c3960)
    values += [rng.randrange(-(1 << 64) + 1, 1 << 64) for _ in range(1024)]
    rows = [(*integer_extended(n), 0 if -(1 << 63) <= n < (1 << 63) else 3,
             n & ((1 << 64) - 1)) for n in values]
    rows.append((0, 0, 0x8000, 0, 0))
    # Rational oracle also exercises fractional lower bits, not only integers.
    for exponent in (-1, 0, 1, 20, 31, 32, 52, 62):
        for sign in (1, -1):
            for significand in ((1 << 63) | 1, (1 << 63) | (1 << 31), (1 << 64) - 1):
                value = Fraction(sign * significand, 1 << (63 - exponent))
                exact = value.denominator == 1
                rows.append((significand & 0xffffffff, significand >> 32,
                             (exponent + 16383) | (0x8000 if sign < 0 else 0),
                             0 if exact else 1, int(value) & ((1 << 64) - 1)))
    return rows


def gp_rows():
    words = [0, 0x80000000, 1, 0x80000001, 0x7f800000, 0xff800000,
             0x7fc00000, 0x7f800001, 0x5f000000, 0xdf000000, 0x5effffff]
    words += [(sign << 31) | (exponent << 23) | fraction
              for sign in range(2) for exponent in range(1, 255)
              for fraction in (0, 1, 0x7fffff)]
    rows = []
    for bits in words:
        value = struct.unpack("<f", struct.pack("<I", bits))[0]
        if (bits >> 23) & 255 == 255:
            kind, result = 2, 0
        elif value < -(1 << 63) or value >= 1 << 63:
            kind, result = 3, 0
        elif not value.is_integer():
            kind, result = 1, 0
        else:
            kind, result = 0, int(value) & ((1 << 64) - 1)
        rows.append((bits, kind, result))
    return rows


def table(rows):
    return ",\n".join("{" + ",".join(f"{x}ull" for x in row) + "}" for row in rows)


class CVTZRILNativeTests(unittest.TestCase):
    def test_encoding_and_refused_forms(self):
        self.assertEqual(decode(struct.pack("<I", cvtzril()), 0).operands,
                         ("fp0", "g4"))
        for word in (cvtzril(dst=21), cvtzril(src=4), cvtzril(src=16),
                     cvtzril(src=22), cvtzril() | 0x20, cvtzril() | 0x40,
                     cvtzril() | 0x2000, cvtzril() | (1 << 14),
                     cvtzril() & ~0x1000):
            self.assertIn(0, emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)[1].unsupported)

    def test_exact_extended_and_fractional_range_boundaries(self):
        native([cvtzril(), 0xffffffff],
               "static const std::uint64_t rows[][5]={" + table(fp_rows()) + "};\n" + COMMON + r"""
int main() {
    Bus bus{};
    for(const auto& row:rows)for(auto ac:{0u,0xff1f917fu,0x801a1155u}) {
        CPU cpu{};if(!kb_establish_arithmetic_controls(cpu,ac))return 1;
        cpu.fp[0]={static_cast<std::uint32_t>(row[0]),static_cast<std::uint32_t>(row[1]),
                   static_cast<std::uint16_t>(row[2])};cpu.fp_defined[0]=true;
        cpu.r[20]=0xdeadbeefu;cpu.r[21]=0xabcdef01u;
        CPU expected=cpu;
        const bool ok=step(cpu,bus);
        if(row[3]==0u) {
            expected.ip=4u;expected.r[20]=static_cast<std::uint32_t>(row[4]);
            expected.r[21]=static_cast<std::uint32_t>(row[4]>>32u);
            if(!ok||cpu.stop_code!=StopCode::none)return 2;
        } else {
            const auto code=row[3]==1u?StopCode::unsupported_floating_rounding:
                StopCode::unsupported_floating_integer_range;
            if(ok||cpu.stop_code!=code||cpu.stop_ip!=0u)return 3;
        }
        if(!same_data(cpu,expected))return 4;
    }
    return 0;
}
""")

    def test_binary32_and_both_destination_aliases(self):
        native([cvtzril(20, 24, source_fp=False), cvtzril(20, 20, source_fp=False),
                cvtzril(21, 20, source_fp=False), 0xffffffff],
               "static const std::uint64_t rows[][3]={" + table(gp_rows()) + "};\n" + COMMON + r"""
int main() {
    Bus bus{};
    for(const auto& row:rows)for(unsigned form=0;form<3u;++form) {
        CPU cpu{};cpu.ip=form*4u;cpu.r[20]=0xdeadbeefu;cpu.r[21]=0xabcdef01u;
        cpu.r[form==2u?21u:20u]=static_cast<std::uint32_t>(row[0]);
        CPU expected=cpu;const bool ok=step(cpu,bus);
        if(row[1]==0u) {
            expected.ip+=4u;const unsigned d=form==0u?24u:20u;
            expected.r[d]=static_cast<std::uint32_t>(row[2]);
            expected.r[d+1u]=static_cast<std::uint32_t>(row[2]>>32u);
            if(!ok)return 1;
        } else {
            const auto code=row[1]==1u?StopCode::unsupported_floating_rounding:
                row[1]==2u?StopCode::unsupported_floating_format:
                StopCode::unsupported_floating_integer_range;
            if(ok||cpu.stop_code!=code)return 2;
        }
        if(!same_data(cpu,expected))return 3;
    }
    return 0;
}
""")

    def test_special_unknown_reset_pending_and_direct_bounds(self):
        native([cvtzril(), 0xffffffff], COMMON + r"""
int main() {
    Bus bus{};
    for(auto value:{ExtendedReal{1u,0u,0u},ExtendedReal{0u,0x80000000u,0u},
                   ExtendedReal{1u,0u,16383u},ExtendedReal{0u,0x80000000u,0x7fffu},
                   ExtendedReal{1u,0xc0000000u,0xffffu}}) {
        CPU cpu{};cpu.fp[0]=value;cpu.fp_defined[0]=true;
        cpu.r[20]=1u;cpu.r[21]=2u;const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_format ||
           !same_data(cpu,before))return 1;
    }
    CPU cpu{};cpu.fp[0]={0u,0x80000000u,16383u};CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register ||
       !same_data(cpu,before))return 2;
    cpu={};cpu.fp_defined[0]=true;
    if(!frame_init(cpu,0x100u,0u))return 3;
    before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register ||
       !same_data(cpu,before))return 4;
    for(auto dst:{1u,31u,32u,0xffffffffu}) {
        cpu={};before=cpu;
        if(convert_real_to_long_integer_exact(cpu,0u,false,dst)||
           cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 5;
    }
    for(auto src:{4u,32u,0xffffffffu}) {
        cpu={};before=cpu;
        if(convert_real_to_long_integer_exact(cpu,src,true,20u)||
           cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 6;
    }
    cpu={};cpu.pending_integer_overflow={true,0x80u,0x84u};before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::integer_overflow_pending ||
       cpu.stop_ip!=0x80u||!same_data(cpu,before))return 7;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
