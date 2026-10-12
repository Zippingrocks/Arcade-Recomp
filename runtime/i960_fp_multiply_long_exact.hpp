// Intel KB MULRL (79Ch), exact binary64/extended80 normal and signed-zero subset.
// Intel 270567-001, pp. 11-89/90, 12-12..14 and Appendix B. No host FP,
// compiler-specific 128-bit type, inferred AC rounding, or exception delivery.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

struct LongRealProduct128 {
    std::uint64_t low;
    std::uint64_t high;
};

static inline LongRealProduct128 multiply_unsigned_64_wide(std::uint64_t a,
                                                         std::uint64_t b) {
    const std::uint64_t al = static_cast<std::uint32_t>(a);
    const std::uint64_t bl = static_cast<std::uint32_t>(b);
    const std::uint64_t ah = a >> 32u;
    const std::uint64_t bh = b >> 32u;
    const std::uint64_t ll = al * bl;
    const std::uint64_t lh = al * bh;
    const std::uint64_t hl = ah * bl;
    const std::uint64_t hh = ah * bh;
    // The middle sum is at most 3*(2^32-1); its carry fits two bits.
    const std::uint64_t middle = (ll >> 32u) +
        static_cast<std::uint32_t>(lh) + static_cast<std::uint32_t>(hl);
    return {(middle << 32u) | static_cast<std::uint32_t>(ll),
            hh + (lh >> 32u) + (hl >> 32u) + (middle >> 32u)};
}

struct LongRealMultiplyOperand {
    std::uint64_t significand = 0u;
    std::int32_t exponent = 0;
    bool negative = false;
    bool zero = false;
};

static inline bool read_long_real_multiply_operand(CPU& cpu, unsigned source,
                                                   bool fp,
                                                   LongRealMultiplyOperand& out) {
    if (fp ? source >= 4u : source >= 32u || (source & 1u) != 0u)
        return stop(cpu, StopCode::untranslated);
    if (fp) {
        const unsigned index = source & 3u;
        if (!cpu.fp_defined[index])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal value = cpu.fp[index];
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

static inline bool multiply_long_real_exact(CPU& cpu, unsigned first,
                                            bool first_fp, unsigned second,
                                            bool second_fp, unsigned destination,
                                            bool destination_fp) {
    if (destination_fp ? destination >= 4u :
        destination >= 32u || (destination & 1u) != 0u)
        return stop(cpu, StopCode::untranslated);
    LongRealMultiplyOperand a{}, b{};
    // Validate both sources even when the other is zero. Zero must not hide
    // an undefined FP register, infinity, NaN, or noncanonical operand.
    if (!read_long_real_multiply_operand(cpu, first, first_fp, a) ||
        !read_long_real_multiply_operand(cpu, second, second_fp, b))
        return false;
    const bool negative = a.negative != b.negative;
    std::uint64_t result = 0u;
    std::int32_t exponent = 0;
    const bool zero = a.zero || b.zero;
    if (!zero) {
        const LongRealProduct128 product = multiply_unsigned_64_wide(a.significand, b.significand);
        // Two normalized 64-bit significands give a 127- or 128-bit product.
        const bool high = (product.high & (std::uint64_t{1} << 63u)) != 0u;
        exponent = a.exponent + b.exponent + (high ? 1 : 0);
        const std::int32_t minimum = destination_fp ? -16382 : -1022;
        const std::int32_t maximum = destination_fp ? 16383 : 1023;
        if (exponent < minimum || exponent > maximum)
            return stop(cpu, StopCode::unsupported_floating_format);
        if (destination_fp) {
            // Keep 64 bits: discard 63 or 64. Never shift a host word by 64.
            const std::uint64_t discarded = high ? product.low :
                product.low & 0x7fffffffffffffffull;
            if (discarded != 0u)
                return stop(cpu, StopCode::unsupported_floating_rounding);
            result = high ? product.high : (product.high << 1u) | (product.low >> 63u);
        } else {
            // Keep 53 bits: discard the low word plus 10 or 11 high-word bits.
            const unsigned shift = high ? 11u : 10u;
            if (product.low != 0u || (product.high & ((std::uint64_t{1} << shift) - 1u)) != 0u)
                return stop(cpu, StopCode::unsupported_floating_rounding);
            result = product.high >> shift;
        }
    }

    // All reads and exactness checks finish before either destination half
    // or its FP knowledge marker changes, including same-register aliases.
    if (destination_fp) {
        const unsigned biased = zero ? 0u : static_cast<unsigned>(exponent + 16383);
        cpu.fp[destination] = {static_cast<std::uint32_t>(result),
            static_cast<std::uint32_t>(result >> 32u),
            static_cast<std::uint16_t>(biased | (negative ? 0x8000u : 0u))};
        cpu.fp_defined[destination] = true;
    } else {
        const std::uint64_t biased = zero ? 0u : static_cast<std::uint64_t>(exponent + 1023);
        const std::uint64_t bits = (negative ? std::uint64_t{1} << 63u : 0u) |
            (biased << 52u) | (result & 0x000fffffffffffffull);
        cpu.r[destination] = static_cast<std::uint32_t>(bits);
        cpu.r[destination + 1u] = static_cast<std::uint32_t>(bits >> 32u);
    }
    return true;
}

} // namespace arcaderecomp_generated
