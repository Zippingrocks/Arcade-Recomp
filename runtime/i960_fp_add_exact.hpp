// ArcadeRecomp — exact, finite IEEE binary32 ADDR (80960KB 78F).
// Original HOTD1 candidate 0x00000C00 uses GPR values and an aliased
// destination. No host float operations or inferred Sega exceptions.
//
// This is deliberately NOT a full floating-point ADDR: signed-zero
// cancellation, non-normal values, overflow/underflow and inexact
// rounding stop before changing the destination. 80960KB AC rounding
// controls, precision flags and exception delivery remain unfinished.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool add_real32_exact(CPU& cpu, std::uint32_t lhs_bits,
                                    std::uint32_t rhs_bits,
                                    unsigned destination) {
    if (destination >= 32u)
        return stop(cpu, StopCode::untranslated);

    const std::uint32_t lhs_exp = (lhs_bits >> 23u) & 255u;
    const std::uint32_t rhs_exp = (rhs_bits >> 23u) & 255u;
    const std::uint32_t lhs_frac = lhs_bits & 0x7fffffu;
    const std::uint32_t rhs_frac = rhs_bits & 0x7fffffu;
    const bool lhs_zero = lhs_exp == 0u && lhs_frac == 0u;
    const bool rhs_zero = rhs_exp == 0u && rhs_frac == 0u;
    if ((lhs_exp == 0u && !lhs_zero) || lhs_exp == 255u ||
        (rhs_exp == 0u && !rhs_zero) || rhs_exp == 255u)
        return stop(cpu, StopCode::unsupported_floating_format);

    if (lhs_zero && rhs_zero) {
        // Sign of (+0)+(-0) depends on rounding mode on some CPUs.
        if (((lhs_bits ^ rhs_bits) & 0x80000000u) != 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        cpu.r[destination] = lhs_bits;
        return true;
    }
    if (lhs_zero || rhs_zero) {
        cpu.r[destination] = lhs_zero ? rhs_bits : lhs_bits;
        return true;
    }

    const std::int32_t left_exponent =
        static_cast<std::int32_t>(lhs_exp) - 127;
    const std::int32_t right_exponent =
        static_cast<std::int32_t>(rhs_exp) - 127;
    const std::int32_t base_exp = left_exponent < right_exponent ?
        left_exponent : right_exponent;
    const unsigned left_shift =
        static_cast<unsigned>(left_exponent - base_exp);
    const unsigned right_shift =
        static_cast<unsigned>(right_exponent - base_exp);
    // No potentially unbounded shifts or signed overflow. A larger exponent
    // gap would discard nonzero bits in binary32, and needs FP precision state.
    if (left_shift > 32u || right_shift > 32u)
        return stop(cpu, StopCode::unsupported_floating_rounding);

    const std::uint64_t lhs_magnitude =
        (static_cast<std::uint64_t>(0x800000u | lhs_frac)) << left_shift;
    const std::uint64_t rhs_magnitude =
        (static_cast<std::uint64_t>(0x800000u | rhs_frac)) << right_shift;
    const std::int64_t lhs_signed =
        (lhs_bits & 0x80000000u) ?
        -static_cast<std::int64_t>(lhs_magnitude) :
        static_cast<std::int64_t>(lhs_magnitude);
    const std::int64_t rhs_signed =
        (rhs_bits & 0x80000000u) ?
        -static_cast<std::int64_t>(rhs_magnitude) :
        static_cast<std::int64_t>(rhs_magnitude);
    const std::int64_t signed_sum = lhs_signed + rhs_signed;
    if (signed_sum == 0)
        return stop(cpu, StopCode::unsupported_floating_rounding);

    const bool negative = signed_sum < 0;
    const std::uint64_t magnitude = negative ?
        static_cast<std::uint64_t>(-signed_sum) :
        static_cast<std::uint64_t>(signed_sum);
    unsigned top_bit = 0u;
    std::uint64_t scan = magnitude;
    while ((scan >>= 1u) != 0u) ++top_bit;
    const std::int32_t output_exponent =
        base_exp - 23 + static_cast<std::int32_t>(top_bit);
    if (output_exponent < -126 || output_exponent > 127)
        return stop(cpu, StopCode::unsupported_floating_format);

    std::uint64_t normalized = 0u;
    if (top_bit > 23u) {
        const unsigned lost = top_bit - 23u;
        if ((magnitude & ((std::uint64_t{1} << lost)-1u)) != 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        normalized = magnitude >> lost;
    } else {
        normalized = magnitude << (23u - top_bit);
    }
    cpu.r[destination] = (negative ? 0x80000000u : 0u) |
        (static_cast<std::uint32_t>(output_exponent+127) << 23u) |
        (static_cast<std::uint32_t>(normalized) & 0x7fffffu);
    return true;
}
} // namespace arcaderecomp_generated
