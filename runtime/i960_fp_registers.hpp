// ArcadeRecomp — bit-exact Intel 80960KB MOVRE data movement.
// Source: Intel 80960KB Programmer's Reference Manual (1988), MOVRE and
// floating-point register representation. No host floating-point operations:
// this does not claim correct rounding, exceptions, or a complete FPU.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool move_extended_real(CPU& cpu, unsigned source,
                                      bool source_fp, unsigned destination,
                                      bool destination_fp) {
    // The AOT translator normally rejects these forms before execution.
    // Check again for anyone invoking the helper directly.
    if (!source_fp && !destination_fp)
        return stop(cpu, StopCode::untranslated);
    if ((source_fp ? source >= 4u :
         source >= 32u || (source & 3u) != 0u) ||
        (destination_fp ? destination >= 4u :
         destination >= 32u || (destination & 3u) != 0u))
        return stop(cpu, StopCode::untranslated);
    if (source_fp && !cpu.fp_defined[source])
        return stop(cpu, StopCode::undefined_floating_point_register);

    // Gather source bits before writing destination. Moving an FP register to
    // a 96-bit general-register triple zero-pads only bits 95:80.
    const ExtendedReal value = source_fp ? cpu.fp[source] :
        ExtendedReal{cpu.r[source], cpu.r[source + 1u],
                     static_cast<std::uint16_t>(cpu.r[source + 2u] & 0xffffu)};
    if (destination_fp) {
        cpu.fp[destination] = value;
        cpu.fp_defined[destination] = true;
    } else {
        cpu.r[destination] = value.low;
        cpu.r[destination + 1u] = value.middle;
        cpu.r[destination + 2u] = static_cast<std::uint32_t>(value.high);
    }
    return true;
}

} // namespace arcaderecomp_generated
