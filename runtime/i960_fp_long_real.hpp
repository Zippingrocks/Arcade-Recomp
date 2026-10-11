// ArcadeRecomp: conservative Intel 80960KB MOVRL 64-bit <-> 80-bit conversion.
// Intel 80960KB Programmer's Reference Manual (Mar 1988), MOVRL and real
// register formats. Never use the host FPU to infer Sega floating controls.
// Normal finite values and both signed zeros are exact. Other encodings,
// denormals, overflow/underflow and inexact conversion remain deliberate stops.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool move_long_real_exact(CPU& cpu, unsigned source,
                                        bool source_fp, unsigned destination,
                                        bool destination_fp) {
    if (!source_fp && !destination_fp)
        return stop(cpu, StopCode::untranslated);
    if ((source_fp ? source >= 4u :
         source >= 32u || (source & 1u) != 0u) ||
        (destination_fp ? destination >= 4u :
         destination >= 32u || (destination & 1u) != 0u))
        return stop(cpu, StopCode::untranslated);
    if (source_fp && !cpu.fp_defined[source])
        return stop(cpu, StopCode::undefined_floating_point_register);

    if (!source_fp) {
        if (!destination_fp)
            return stop(cpu, StopCode::untranslated);
        const std::uint64_t bits = static_cast<std::uint64_t>(cpu.r[source]) |
            (static_cast<std::uint64_t>(cpu.r[source + 1u]) << 32u);
        const std::uint32_t exponent =
            static_cast<std::uint32_t>((bits >> 52u) & 0x7ffu);
        const std::uint64_t fraction = bits & 0x000fffffffffffffull;
        const std::uint16_t sign = (bits >> 63u) ?
            static_cast<std::uint16_t>(0x8000u) : 0u;
        ExtendedReal value{};
        if (exponent == 0u && fraction == 0u) {
            value.high = sign;  // preserve negative zero
        } else if (exponent == 0u || exponent == 0x7ffu) {
            // Denormals, infinities and NaNs require independent
            // arithmetic-control and floating exception semantics.
            return stop(cpu, StopCode::unsupported_floating_format);
        } else {
            const std::uint64_t significand =
                ((std::uint64_t{1} << 52u) | fraction) << 11u;
            value.low = static_cast<std::uint32_t>(significand);
            value.middle = static_cast<std::uint32_t>(significand >> 32u);
            value.high = static_cast<std::uint16_t>(
                sign | static_cast<std::uint16_t>(exponent + 15360u));
        }
        // GP -> GP move is conservatively left untranslated by the emitter.
        cpu.fp[destination] = value;
        cpu.fp_defined[destination] = true;
        return true;
    }

    const ExtendedReal value = cpu.fp[source];
    if (destination_fp) {
        // Both operands use the same 80-bit format; do not normalize bits.
        cpu.fp[destination] = value;
        cpu.fp_defined[destination] = true;
        return true;
    }
    const std::uint16_t exponent =
        static_cast<std::uint16_t>(value.high & 0x7fffu);
    const std::uint64_t significand =
        static_cast<std::uint64_t>(value.low) |
        (static_cast<std::uint64_t>(value.middle) << 32u);
    const std::uint64_t sign = (value.high & 0x8000u) ?
        (std::uint64_t{1} << 63u) : 0u;
    std::uint64_t bits = sign;
    if (exponent == 0u && significand == 0u) {
        // Negative zero retains its sign.
    } else if (exponent < 15361u || exponent > 17406u ||
               (significand & (std::uint64_t{1} << 63u)) == 0u) {
        // Noncanonical extended formats, exponents needing binary64
        // underflow/overflow handling, infinities, NaNs: refuse to guess.
        return stop(cpu, StopCode::unsupported_floating_format);
    } else if ((significand & 0x7ffu) != 0u) {
        // AC rounding mode and inexact fault behavior are unimplemented.
        return stop(cpu, StopCode::unsupported_floating_rounding);
    } else {
        const std::uint64_t biased_exponent =
            static_cast<std::uint64_t>(exponent - 15360u);
        bits |= (biased_exponent << 52u) |
            ((significand >> 11u) & 0x000fffffffffffffull);
    }
    // No writes until both validation and conversion have succeeded.
    cpu.r[destination] = static_cast<std::uint32_t>(bits);
    cpu.r[destination + 1u] = static_cast<std::uint32_t>(bits >> 32u);
    return true;
}

} // namespace arcaderecomp_generated
