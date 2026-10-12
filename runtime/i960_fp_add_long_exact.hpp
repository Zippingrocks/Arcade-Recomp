// Intel KB ADDRL (79Fh), exact normal/signed-zero binary64/extended80 addition.
// Intel 270567-001, pp. 11-8/9, 3-11, 12-12..14 and Appendix B.
#pragma once
#include "i960_fp_long_operand.hpp"
#include "i960_arithmetic_controls.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool long_real_cancellation_sign(CPU& cpu, bool& negative) {
    const auto ac = kb_arithmetic_controls_snapshot(cpu);
    constexpr std::uint32_t mask = 0xc0000000u;
    constexpr std::uint32_t down = 0x40000000u;
    // Any known bit disagreeing with 01 proves the mode is NOT round-down.
    // Otherwise both rounding bits must be known to distinguish -0 from +0.
    if (((ac.value ^ down) & ac.known_mask & mask) != 0u) {
        negative = false;
        return true;
    }
    if ((ac.known_mask & mask) != mask)
        return stop(cpu, StopCode::undefined_arithmetic_controls);
    negative = true;
    return true;
}

static inline bool add_long_real_exact(CPU& cpu, unsigned first, bool first_fp,
                                       unsigned second, bool second_fp,
                                       unsigned destination, bool destination_fp) {
    if (destination_fp ? destination >= 4u :
        destination >= 32u || (destination & 1u) != 0u)
        return stop(cpu, StopCode::untranslated);
    LongRealOperand a{}, b{};
    if (!read_long_real_normal_operand(cpu, first, first_fp, a) ||
        !read_long_real_normal_operand(cpu, second, second_fp, b))
        return false;

    // Accumulate magnitude in two portable 64-bit limbs. No signed products,
    // compiler-specific wide type, host FP, or discarded alignment bits.
    std::uint64_t low = 0u, high = 0u;
    std::int32_t base = 0;
    bool negative = a.negative;
    bool zero = a.zero && b.zero;
    if (zero) {
        if (a.negative != b.negative && !long_real_cancellation_sign(cpu, negative))
            return false;
    } else if (a.zero || b.zero) {
        const LongRealOperand& nonzero = a.zero ? b : a;
        low = nonzero.significand;
        base = nonzero.exponent;
        negative = nonzero.negative;
    } else {
        // Larger magnitude first: differing normal exponents determine order.
        if (a.exponent < b.exponent ||
            (a.exponent == b.exponent && a.significand < b.significand)) {
            const LongRealOperand swap = a; a = b; b = swap;
        }
        const unsigned gap = static_cast<unsigned>(a.exponent - b.exponent);
        // Beyond 64, even opposite-sign subtraction requires >64 significant
        // bits. At gap==64, 2^64-1 can still be exact, so retain that boundary.
        if (gap > 64u) {
            // Such a small second operand cannot carry into the next binade.
            // Subtracting from an exact power of two drops one exponent bit.
            const std::int32_t output_exponent = a.exponent -
                (a.negative != b.negative && a.significand == (std::uint64_t{1} << 63u) ? 1 : 0);
            if (output_exponent < (destination_fp ? -16382 : -1022) ||
                output_exponent > (destination_fp ? 16383 : 1023))
                return stop(cpu, StopCode::unsupported_floating_format);
            return stop(cpu, StopCode::unsupported_floating_rounding);
        }
        base = b.exponent;
        negative = a.negative;
        if (gap == 0u) low = a.significand;
        else if (gap == 64u) high = a.significand;
        else {
            low = a.significand << gap;
            high = a.significand >> (64u - gap);
        }
        if (a.negative == b.negative) {
            const std::uint64_t previous = low;
            low += b.significand;
            high += low < previous ? 1u : 0u;
        } else {
            const bool borrow = low < b.significand;
            low -= b.significand;
            high -= borrow ? 1u : 0u;
        }
        zero = low == 0u && high == 0u;
        if (zero && !long_real_cancellation_sign(cpu, negative)) return false;
    }

    std::uint64_t result = 0u;
    std::int32_t exponent = 0;
    if (!zero) {
        unsigned top = high != 0u ? 64u : 0u;
        for (std::uint64_t scan = high != 0u ? high : low; (scan >>= 1u) != 0u;) ++top;
        exponent = base - 63 + static_cast<std::int32_t>(top);
        const std::int32_t minimum = destination_fp ? -16382 : -1022;
        const std::int32_t maximum = destination_fp ? 16383 : 1023;
        if (exponent < minimum || exponent > maximum)
            return stop(cpu, StopCode::unsupported_floating_format);
        const unsigned last = destination_fp ? 63u : 52u;
        if (top > last) {
            const unsigned shift = top - last;
            if (shift >= 64u) {
                const unsigned upper_shift = shift - 64u; // 0..11
                if (low != 0u || (high & ((std::uint64_t{1} << upper_shift) - 1u)) != 0u)
                    return stop(cpu, StopCode::unsupported_floating_rounding);
                result = high >> upper_shift;
            } else {
                if ((low & ((std::uint64_t{1} << shift) - 1u)) != 0u)
                    return stop(cpu, StopCode::unsupported_floating_rounding);
                result = (low >> shift) | (high << (64u - shift));
            }
        } else {
            result = low << (last - top);
        }
    }
    // All source/control reads and checks precede both destination halves.
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
