// Canonical normal/signed-zero binary64 GPR-pair or extended80 FP source.
// Intel 270567-001, pp. 12-7..14. Shared by exact long-real arithmetic.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
struct LongRealOperand {
    std::uint64_t significand = 0u;
    std::int32_t exponent = 0;
    bool negative = false;
    bool zero = false;
};

static inline bool read_long_real_normal_operand(CPU& cpu, unsigned source,
                                                 bool fp, LongRealOperand& out) {
    if (fp ? source >= 4u : source >= 32u || (source & 1u) != 0u)
        return stop(cpu, StopCode::untranslated);
    if (fp) {
        if (!cpu.fp_defined[source])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal value = cpu.fp[source];
        const unsigned exponent = value.high & 0x7fffu;
        out.negative = (value.high & 0x8000u) != 0u;
        out.significand = (static_cast<std::uint64_t>(value.middle) << 32u) | value.low;
        out.zero = exponent == 0u && out.significand == 0u;
        if (!out.zero && (exponent == 0u || exponent == 0x7fffu ||
                         (value.middle & 0x80000000u) == 0u))
            return stop(cpu, StopCode::unsupported_floating_format);
        out.exponent = static_cast<std::int32_t>(exponent) - 16383;
    } else {
        const std::uint64_t bits = static_cast<std::uint64_t>(cpu.r[source]) |
            (static_cast<std::uint64_t>(cpu.r[source + 1u]) << 32u);
        const unsigned exponent = static_cast<unsigned>((bits >> 52u) & 0x7ffu);
        const std::uint64_t fraction = bits & 0x000fffffffffffffull;
        out.negative = (bits >> 63u) != 0u;
        out.zero = exponent == 0u && fraction == 0u;
        if ((!out.zero && exponent == 0u) || exponent == 0x7ffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        out.exponent = static_cast<std::int32_t>(exponent) - 1023;
        out.significand = out.zero ? 0u : ((std::uint64_t{1} << 52u) | fraction) << 11u;
    }
    return true;
}
} // namespace arcaderecomp_generated
