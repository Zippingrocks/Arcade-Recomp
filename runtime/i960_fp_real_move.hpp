// ArcadeRecomp: Intel 80960KB MOVR exact real32 / extended80 movement.
// Intel 80960KB Programmer's Reference Manual (Mar 1988), pp. 11-86/87,
// 12-10, 12-15. Integer bit operations only; no host floating-point controls.
// Signed zeros and canonical finite normal values are supported. Special,
// denormal and inexact conversions require unimplemented Intel FP handling.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool move_real_exact(CPU& cpu, unsigned source,
                                   bool source_fp, unsigned destination,
                                   bool destination_fp) {
    if ((source_fp ? source >= 4u : source >= 32u) ||
        (destination_fp ? destination >= 4u : destination >= 32u))
        return stop(cpu, StopCode::untranslated);
    if (source_fp && !cpu.fp_defined[source])
        return stop(cpu, StopCode::undefined_floating_point_register);

    if (!source_fp) {
        const std::uint32_t bits = cpu.r[source];
        const std::uint32_t exponent = (bits >> 23u) & 0xffu;
        const std::uint32_t fraction = bits & 0x7fffffu;
        if ((exponent == 0u && fraction != 0u) || exponent == 0xffu)
            return stop(cpu, StopCode::unsupported_floating_format);
        if (!destination_fp) {
            // Same-format numeric move. Validation above is still necessary:
            // MOVR is not the arbitrary bit transfer provided by integer MOV.
            cpu.r[destination] = bits;
            return true;
        }
        ExtendedReal value{};
        value.high = static_cast<std::uint16_t>((bits >> 16u) & 0x8000u);
        if (exponent != 0u) {
            value.middle = (0x800000u | fraction) << 8u;
            value.high = static_cast<std::uint16_t>(
                value.high | (exponent + 16256u));
        }
        cpu.fp[destination] = value;
        cpu.fp_defined[destination] = true;
        return true;
    }

    // Capture before destination changes, including fpN -> fpN aliases.
    const ExtendedReal value = cpu.fp[source];
    const std::uint16_t exponent = value.high & 0x7fffu;
    const std::uint64_t significand =
        (static_cast<std::uint64_t>(value.middle) << 32u) | value.low;
    const bool zero = exponent == 0u && significand == 0u;
    if (!zero && (exponent == 0u || exponent == 0x7fffu ||
                  (value.middle & 0x80000000u) == 0u))
        return stop(cpu, StopCode::unsupported_floating_format);
    if (destination_fp) {
        // FP operands are already extended80, independent of MOVR's suffix.
        // Preserve their full precision; do not narrow through binary32.
        cpu.fp[destination] = value;
        cpu.fp_defined[destination] = true;
        return true;
    }

    std::uint32_t bits = static_cast<std::uint32_t>(value.high & 0x8000u) << 16u;
    if (!zero) {
        if (exponent < 16257u || exponent > 16510u)
            return stop(cpu, StopCode::unsupported_floating_format);
        if ((significand & 0xffffffffffull) != 0u)
            return stop(cpu, StopCode::unsupported_floating_rounding);
        bits |= (static_cast<std::uint32_t>(exponent - 16256u) << 23u) |
                (static_cast<std::uint32_t>(significand >> 40u) & 0x7fffffu);
    }
    // No architectural mutation until validation and exact conversion finish.
    cpu.r[destination] = bits;
    return true;
}

} // namespace arcaderecomp_generated
