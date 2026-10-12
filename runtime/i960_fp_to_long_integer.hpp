// Intel KB CVTZRIL (6C3h), exact real32/extended80 -> signed 64-bit integer.
// Intel 270567-001, pp. 11-50/51 and Appendix B. Fractional inputs, specials
// and overflow remain diagnostic stops; no invented fault state or saturation.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool convert_real_to_long_integer_exact(CPU& cpu, unsigned source,
                                                      bool source_fp,
                                                      unsigned destination) {
    if (source >= (source_fp ? 4u : 32u) || destination >= 32u ||
        (destination & 1u) != 0u)
        return stop(cpu, StopCode::untranslated);
    std::uint64_t significand = 0u;
    std::int32_t exponent = 0;
    unsigned fraction_position = 0;
    bool negative = false;
    bool zero = false;
    if (source_fp) {
        const unsigned index = source & 3u;
        if (!cpu.fp_defined[index])
            return stop(cpu, StopCode::undefined_floating_point_register);
        const ExtendedReal value = cpu.fp[index];
        const unsigned raw_exp = value.high & 0x7fffu;
        negative = (value.high & 0x8000u) != 0u;
        significand = (static_cast<std::uint64_t>(value.middle) << 32u) | value.low;
        zero = raw_exp == 0u && significand == 0u;
        if (!zero && (raw_exp == 0u || raw_exp == 0x7fffu ||
                      (value.middle & 0x80000000u) == 0u))
            return stop(cpu, StopCode::unsupported_floating_format);
        exponent = static_cast<std::int32_t>(raw_exp) - 16383;
        fraction_position = 63u;
    } else {
        const std::uint32_t value = cpu.r[source];
        const unsigned raw_exp = (value >> 23u) & 0xffu;
        const std::uint32_t fraction = value & 0x7fffffu;
        negative = (value & 0x80000000u) != 0u;
        zero = raw_exp == 0u && fraction == 0u;
        if (raw_exp == 0xffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        if (!zero && raw_exp == 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        significand = 0x800000u | fraction;
        exponent = static_cast<std::int32_t>(raw_exp) - 127;
        fraction_position = 23u;
    }

    std::uint64_t magnitude = 0u;
    if (!zero) {
        if (exponent < 0)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        if (exponent > 63)
            return stop(cpu, StopCode::unsupported_floating_integer_range);
        if (static_cast<unsigned>(exponent) <= fraction_position) {
            const unsigned shift = fraction_position - static_cast<unsigned>(exponent);
            const std::uint64_t discarded = shift == 0u ? 0u :
                (std::uint64_t{1} << shift) - 1u;
            if ((significand & discarded) != 0u)
                return stop(cpu, StopCode::unsupported_floating_rounding);
            magnitude = significand >> shift;
        } else {
            // Only binary32 takes this path: at most a 40-bit left shift,
            // so its 24-bit significand fits within unsigned 64-bit storage.
            magnitude = significand << (static_cast<unsigned>(exponent) - fraction_position);
        }
        const std::uint64_t limit = negative ? (std::uint64_t{1} << 63u) :
            (std::uint64_t{1} << 63u) - 1u;
        if (magnitude > limit)
            return stop(cpu, StopCode::unsupported_floating_integer_range);
    }
    const std::uint64_t result = negative ? std::uint64_t{0} - magnitude : magnitude;
    // Capture/validate everything before touching either half, including aliases.
    cpu.r[destination] = static_cast<std::uint32_t>(result);
    cpu.r[destination + 1u] = static_cast<std::uint32_t>(result >> 32u);
    return true;
}

} // namespace arcaderecomp_generated
