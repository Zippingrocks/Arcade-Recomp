// Intel 80960KB SCALER (677h), exact normal binary32 GPR subset.
// Primary reference: Intel KB Programmer's Reference Manual (Mar 1988),
// pp. 11-105--11-106. src1 is signed integer; src2/dst are reals.
// No host floating-point arithmetic or rounding mode is consulted.
// Extended registers, nonnormal operands/results and FP faults remain open.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool scale_real32_exact(CPU& cpu, std::uint32_t power_bits,
                                      std::uint32_t source_bits,
                                      unsigned destination) {
    if (destination >= 32u)
        return stop(cpu, StopCode::untranslated);
    const std::uint32_t exponent = (source_bits >> 23u) & 255u;
    if (exponent == 0u || exponent == 255u)
        return stop(cpu, StopCode::unsupported_floating_format);
    // Decode signed int32 without implementation-defined unsigned->signed
    // conversion. Wide addition makes INT_MIN/INT_MAX counts safe.
    const std::int64_t power = (power_bits & 0x80000000u) ?
        -(std::int64_t{0x100000000} - power_bits) :
        static_cast<std::int64_t>(power_bits);
    const std::int64_t next_exponent = exponent + power;
    if (next_exponent < 1 || next_exponent > 254)
        return stop(cpu, StopCode::unsupported_floating_format);
    // Scaling a normal to another normal changes only the exponent. Every
    // significand bit is retained, so this subset needs no rounding/flags.
    cpu.r[destination] = (source_bits & 0x807fffffu) |
        (static_cast<std::uint32_t>(next_exponent) << 23u);
    return true;
}
} // namespace arcaderecomp_generated
