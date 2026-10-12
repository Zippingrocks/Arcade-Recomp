// Original Intel 80960KB arithmetic-controls composition and MODAC (645h).
// Intel 270567-001 (1988), pp. 3-7..3-11 and 11-79.
// This stores controls; it does not implement FP rounding or fault delivery.
#pragma once
#include "i960_integer_arithmetic.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static constexpr std::uint32_t KB_AC_DEFINED_FIELDS = 0xff1f917fu;
static constexpr std::uint32_t KB_AC_LEGACY_FIELDS = 0x00001107u;

struct KBArithmeticControlsSnapshot {
    std::uint32_t value = 0;
    std::uint32_t known_mask = 0;
};

// Existing comparisons, synchronous transfers and integer arithmetic keep
// their live CC/overflow fields. Compose those on every read so a later
// MODAC cannot observe stale flags from a previous full-word snapshot.
inline KBArithmeticControlsSnapshot kb_arithmetic_controls_snapshot(
        const CPU& cpu) {
    KBArithmeticControlsSnapshot result{
        cpu.arithmetic_controls_other & ~KB_AC_LEGACY_FIELDS,
        cpu.arithmetic_controls_other_defined_mask & ~KB_AC_LEGACY_FIELDS};
    result.value |= static_cast<std::uint32_t>(cpu.cc) & 7u;
    if (cpu.cc_defined && cpu.cc >= 0 && cpu.cc <= 7)
        result.known_mask |= 7u;
    if (cpu.integer_overflow_mask) result.value |= 0x1000u;
    if (cpu.integer_overflow_mask_defined) result.known_mask |= 0x1000u;
    if (cpu.integer_overflow_flag) result.value |= 0x100u;
    if (cpu.integer_overflow_flag_defined) result.known_mask |= 0x100u;
    return result;
}

// Explicit control-state import for a verified capture or synthetic fixture.
// This is never called automatically at reset. Reject reserved-one values
// instead of silently turning unsupported inputs into a fabricated AC word.
inline bool kb_establish_arithmetic_controls(CPU& cpu, std::uint32_t value) {
    if (value & ~KB_AC_DEFINED_FIELDS) return false;
    cpu.arithmetic_controls_other = value & ~KB_AC_LEGACY_FIELDS;
    cpu.arithmetic_controls_other_defined_mask = ~KB_AC_LEGACY_FIELDS;
    cpu.cc = static_cast<int>(value & 7u);
    cpu.cc_defined = true;
    cpu.integer_overflow_mask = (value & 0x1000u) != 0u;
    cpu.integer_overflow_mask_defined = true;
    cpu.integer_overflow_flag = (value & 0x100u) != 0u;
    cpu.integer_overflow_flag_defined = true;
    return true;
}

inline bool kb_modac_checked(CPU& cpu, std::uint32_t mask,
                             std::uint32_t source, unsigned destination) {
    if (cpu.pending_integer_overflow.pending)
        return stop_pending_integer_overflow(cpu);
    if (destination >= 32u)
        return stop(cpu, StopCode::untranslated);
    const auto previous = kb_arithmetic_controls_snapshot(cpu);
    // MODAC returns ALL of the previous AC in a GPR, even when the mask
    // overwrites every bit. Unknown old controls cannot be materialized as
    // known register data until general-register unknownness is supported.
    if (previous.known_mask != 0xffffffffu)
        return stop(cpu, StopCode::undefined_arithmetic_controls);
    const std::uint32_t updated =
        (source & mask) | (previous.value & ~mask);
    if ((previous.value | updated) & ~KB_AC_DEFINED_FIELDS)
        return stop(cpu, StopCode::reserved_arithmetic_controls);
    // Sources are passed by value before this destination mutation, making
    // every source/destination alias (including all three equal) safe.
    if (!kb_establish_arithmetic_controls(cpu, updated))
        return stop(cpu, StopCode::reserved_arithmetic_controls);
    cpu.r[destination] = previous.value;
    return true;
}

} // namespace arcaderecomp_generated
