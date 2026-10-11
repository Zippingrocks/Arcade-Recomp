// ArcadeRecomp — Intel 80960KB CVTZRI (6C2), exact-input subset.
// Round toward zero is the documented operation. This implements values
// that are ALREADY exact signed integers; precision status and invalid
// arithmetic exception delivery remain unavailable. Fractional and
// out-of-range cases fail closed before changing the destination.
//
// All extraction is unsigned integer arithmetic on IEEE binary32 or
// explicit 80-bit extended-real bits: no host floating-point dependency.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool convert_real_to_integer_exact(CPU& cpu, unsigned source,
                                                 bool source_fp,
                                                 unsigned destination) {
    if (source >= (source_fp ? 4u : 32u) || destination >= 32u)
        return stop(cpu, StopCode::untranslated);

    bool negative = false;
    std::uint64_t significand = 0u;
    std::int32_t exponent = 0;
    unsigned fraction_position = 0;

    if (source_fp) {
        if (!cpu.fp_defined[source])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal source_bits = cpu.fp[source];
        const std::uint32_t raw_exp = source_bits.high & 0x7fffu;
        negative = (source_bits.high & 0x8000u) != 0u;
        significand = static_cast<std::uint64_t>(source_bits.low) |
            (static_cast<std::uint64_t>(source_bits.middle) << 32u);
        if (raw_exp == 0u && significand == 0u) {
            cpu.r[destination] = 0u; // both zero signs are exact
            return true;
        }
        if (raw_exp == 0u || raw_exp == 0x7fffu ||
            (significand & (std::uint64_t{1} << 63u)) == 0u)
            return stop(cpu, StopCode::unsupported_floating_format);
        exponent = static_cast<std::int32_t>(raw_exp) - 16383;
        fraction_position = 63u;
    } else {
        const std::uint32_t bits = cpu.r[source];
        const std::uint32_t raw_exp = (bits >> 23u) & 0xffu;
        negative = (bits & 0x80000000u) != 0u;
        const std::uint32_t fraction = bits & 0x7fffffu;
        if (raw_exp == 0u && fraction == 0u) {
            cpu.r[destination] = 0u;
            return true;
        }
        if (raw_exp == 0xffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        if (raw_exp == 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        significand = static_cast<std::uint64_t>(0x800000u | fraction);
        exponent = static_cast<std::int32_t>(raw_exp) - 127;
        fraction_position = 23u;
    }

    // An exact nonzero integer cannot have a negative binary exponent.
    if (exponent < 0)
        return stop(cpu, StopCode::unsupported_floating_rounding);
    if (exponent > 31)
        return stop(cpu, StopCode::unsupported_floating_integer_range);

    const unsigned shift = fraction_position -
        static_cast<unsigned>(exponent <= static_cast<std::int32_t>(fraction_position)
                              ? exponent : static_cast<std::int32_t>(fraction_position));
    std::uint64_t magnitude = 0u;
    if (exponent <= static_cast<std::int32_t>(fraction_position)) {
        // shift is in [0,63]; the mask expression never shifts by 64.
        const std::uint64_t discarded =
            shift == 0u ? 0u : ((std::uint64_t{1} << shift) - 1u);
        if ((significand & discarded) != 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        magnitude = significand >> shift;
    } else {
        magnitude = significand << (
            static_cast<unsigned>(exponent) - fraction_position);
    }
    const std::uint64_t limit = negative ? 0x80000000ull : 0x7fffffffull;
    if (magnitude > limit)
        return stop(cpu, StopCode::unsupported_floating_integer_range);

    // Source captured before destination update (source may equal dest).
    const std::uint32_t magnitude32 =
        static_cast<std::uint32_t>(magnitude);
    cpu.r[destination] = negative ? (0u - magnitude32) : magnitude32;
    return true;
}
} // namespace arcaderecomp_generated
