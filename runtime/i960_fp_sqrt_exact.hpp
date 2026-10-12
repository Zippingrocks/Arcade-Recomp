// Intel KB SQRTR (688h), exact binary32/extended80 normal and signed-zero subset.
// Intel 270567-001, pp. 11-115/116, 12-12..14 and Appendix B. No host FP,
// inferred rounding, or exception delivery; unsupported inputs stop atomically.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline std::uint64_t sqrt_unsigned_64_floor(std::uint64_t value) {
    std::uint64_t root = 0u;
    // Every trial is at most 2^32-1, whose square fits uint64_t. The fixed
    // descending bit search returns floor(sqrt(value)) without division.
    for (unsigned bit = 32u; bit != 0u; --bit) {
        const std::uint64_t trial = root | (std::uint64_t{1} << (bit - 1u));
        if (trial * trial <= value) root = trial;
    }
    return root;
}

static inline bool square_root_real_exact(CPU& cpu, unsigned source,
                                          bool source_fp, unsigned destination,
                                          bool destination_fp) {
    if (source >= (source_fp ? 4u : 32u) ||
        destination >= (destination_fp ? 4u : 32u))
        return stop(cpu, StopCode::untranslated);
    std::uint64_t significand = 0u;
    std::int32_t power = 0;
    bool negative = false;
    bool zero = false;
    if (source_fp) {
        if (!cpu.fp_defined[source])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal value = cpu.fp[source];
        const unsigned exponent = value.high & 0x7fffu;
        significand = (static_cast<std::uint64_t>(value.middle) << 32u) | value.low;
        negative = (value.high & 0x8000u) != 0u;
        zero = exponent == 0u && significand == 0u;
        if (!zero && (exponent == 0u || exponent == 0x7fffu ||
                      (value.middle & 0x80000000u) == 0u))
            return stop(cpu, StopCode::unsupported_floating_format);
        power = static_cast<std::int32_t>(exponent) - 16383 - 63;
    } else {
        const std::uint32_t bits = cpu.r[source];
        const unsigned exponent = (bits >> 23u) & 0xffu;
        const unsigned fraction = bits & 0x7fffffu;
        negative = (bits & 0x80000000u) != 0u;
        zero = exponent == 0u && fraction == 0u;
        if ((!zero && exponent == 0u) || exponent == 0xffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        significand = zero ? 0u : 0x800000u | fraction;
        power = static_cast<std::int32_t>(exponent) - 127 - 23;
    }

    std::uint64_t result = 0u;
    std::int32_t result_exponent = 0;
    if (!zero) {
        // Negative nonzero needs architected invalid-operation handling.
        if (negative) return stop(cpu, StopCode::unsupported_floating_format);
        // x = odd * 2^power. Its square root is a dyadic rational exactly
        // when power is even and odd is a perfect integer square.
        while ((significand & 1u) == 0u) {
            significand >>= 1u;
            ++power;
        }
        if (power % 2 != 0)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        const std::uint64_t root = sqrt_unsigned_64_floor(significand);
        if (root * root != significand)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        unsigned width = 0u;
        for (std::uint64_t bits = root; bits != 0u; bits >>= 1u) ++width;
        result_exponent = power / 2 + static_cast<std::int32_t>(width) - 1;
        const std::int32_t minimum = destination_fp ? -16382 : -126;
        const std::int32_t maximum = destination_fp ? 16383 : 127;
        if (result_exponent < minimum || result_exponent > maximum)
            return stop(cpu, StopCode::unsupported_floating_format);
        const unsigned precision = destination_fp ? 64u : 24u;
        if (width > precision) {
            const unsigned shift = width - precision;
            if ((root & ((std::uint64_t{1} << shift) - 1u)) != 0u)
                return stop(cpu, StopCode::unsupported_floating_rounding);
            result = root >> shift;
        } else {
            result = root << (precision - width);
        }
    }

    // All source reads, format and exactness checks precede the only write.
    // A successful exact result does not change AC flags or their knownness.
    if (destination_fp) {
        const unsigned exponent = zero ? 0u : static_cast<unsigned>(result_exponent + 16383);
        cpu.fp[destination] = {static_cast<std::uint32_t>(result),
            static_cast<std::uint32_t>(result >> 32u),
            static_cast<std::uint16_t>(exponent | (negative ? 0x8000u : 0u))};
        cpu.fp_defined[destination] = true;
    } else {
        const unsigned exponent = zero ? 0u : static_cast<unsigned>(result_exponent + 127);
        cpu.r[destination] = (negative ? 0x80000000u : 0u) | (exponent << 23u) |
            (static_cast<std::uint32_t>(result) & 0x7fffffu);
    }
    return true;
}

} // namespace arcaderecomp_generated
