// Intel 80960KB CVTIR: conservative, bit-exact integer -> real conversions.
// No arithmetic is delegated to the host floating point environment.
// A conversion requiring AC rounding or masked/unmasked inexact handling
// stops *before* changing destination or IP. See 1988 Intel KB manual,
// Chapters 11 (CVTIR) and 12 (floating-point controls).
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

template<bool destination_fp>
static inline bool convert_integer_to_real_exact(CPU& cpu,
                                                 std::uint32_t integer_bits,
                                                 unsigned destination) {
    if (destination >= (destination_fp ? 4u : 32u))
        return stop(cpu, StopCode::untranslated);
    // Signed 32-bit magnitude in unsigned arithmetic; INT_MIN is safe.
    const bool negative = (integer_bits & 0x80000000u) != 0u;
    const std::uint32_t magnitude =
        negative ? (0u - integer_bits) : integer_bits;
    if (magnitude == 0u) {
        if constexpr (destination_fp) {
            cpu.fp[destination] = {};
            cpu.fp_defined[destination] = true;
        } else {
            cpu.r[destination] = 0u;
        }
        return true;
    }
    unsigned msb = 31u;
    while (((magnitude >> msb) & 1u) == 0u)
        --msb;
    if constexpr (destination_fp) {
        // Integer magnitude <= 2^31: every bit fits in the 64-bit
        // extended-real significand. All conversions here are exact.
        const std::uint64_t significand =
            static_cast<std::uint64_t>(magnitude) << (63u - msb);
        cpu.fp[destination].low =
            static_cast<std::uint32_t>(significand);
        cpu.fp[destination].middle =
            static_cast<std::uint32_t>(significand >> 32u);
        cpu.fp[destination].high = static_cast<std::uint16_t>(
            (negative ? 0x8000u : 0u) | (16383u + msb));
        cpu.fp_defined[destination] = true;
        return true;
    }
    // IEEE-754 binary32 has 24 significant bits. An integer that discards
    // nonzero low bits would depend on unimplemented AC rounding/flags.
    const unsigned lost = (msb > 23u) ? msb - 23u : 0u;
    if (lost != 0u && (magnitude & ((1u << lost) - 1u)) != 0u)
        return stop(cpu, StopCode::unsupported_floating_rounding);
    const std::uint32_t normalized = (msb > 23u) ?
        magnitude >> lost : magnitude << (23u - msb);
    cpu.r[destination] = (negative ? 0x80000000u : 0u) |
        ((msb + 127u) << 23u) | (normalized & 0x7fffffu);
    return true;
}

} // namespace arcaderecomp_generated
