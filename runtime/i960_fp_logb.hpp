// ArcadeRecomp: Intel 80960KB LOGBNR (68Ah), conservative exact subset.
// Intel KB Programmer's Reference Manual (1988), binary logarithm.
// IEEE logb returns the exponent as a floating-point INTEGER, not the
// fractional logarithm; e.g. logb(3249.0) = 11.0.
// No C++ log(), floating arithmetic, or host rounding is used here.
// Values needing special-value/fault handling stop without side effects.
#pragma once
#include "i960_fp_convert.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool log_binary_real_exact(CPU& cpu,
                                         unsigned source, bool source_fp,
                                         unsigned destination, bool dest_fp) {
    if (source >= (source_fp ? 4u : 32u) ||
        destination >= (dest_fp ? 4u : 32u))
        return stop(cpu, StopCode::untranslated);

    std::int32_t exponent = 0;
    if (source_fp) {
        if (!cpu.fp_defined[source])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal value = cpu.fp[source];
        const std::uint32_t raw_exponent = value.high & 0x7fffu;
        // Require canonical finite normal extended80, with explicit
        // significand leading one. Sign is deliberately irrelevant.
        if (raw_exponent == 0u || raw_exponent == 0x7fffu ||
            (value.middle & 0x80000000u) == 0u)
            return stop(cpu, StopCode::unsupported_floating_format);
        exponent = static_cast<std::int32_t>(raw_exponent) - 16383;
    } else {
        const std::uint32_t value = cpu.r[source];
        const std::uint32_t raw_exponent = (value >> 23u) & 0xffu;
        // Exact normal finite values only. Zero, subnormal, infinite and
        // NaN inputs depend on unimplemented FP status/exception semantics.
        if (raw_exponent == 0u || raw_exponent == 0xffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        exponent = static_cast<std::int32_t>(raw_exponent) - 127;
    }
    // The result is always an EXACT integer in [-16382,+16383].
    // Both IEEE binary32 and 80-bit extended can represent that value.
    // Helper captures the signed integer bits and preserves AC.cc.
    return convert_integer_to_real_exact(
        cpu, static_cast<std::uint32_t>(exponent), destination, dest_fp);
}
} // namespace arcaderecomp_generated
