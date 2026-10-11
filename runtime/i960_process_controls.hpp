// Intel 80960KB MODPC (655h): deliberately bounded native subset.
//
// Primary: Intel 80960KB Programmer's Reference Manual (Mar. 1988),
// Chapter 11, MODPC pp. 11-82 to 11-83, Chapter 7 process controls.
//
// src1 is a dummy. src2 MASK selects bits from original src/dst, and the
// destination register receives the *old* process-controls word on success.
// The initial CPU process controls are unknown in strict native execution.
// This cannot stand in for Intel fault entry, interrupt-table pending scan,
// process-mode stack switching or trace-enable propagation.
#pragma once
#include "i960_interrupt_priority.hpp"

#include <cstdint>

namespace arcaderecomp_generated {

static constexpr std::uint32_t KB_PC_PRIORITY_MASK = 0x001f0000u;
static constexpr std::uint32_t KB_PC_SUPERVISOR_BIT = 0x00000002u;

// The interpreter never assumes that a host CPU{}'s zero-initialized
// process_controls word is architected hardware data.
inline bool kb_modpc_checked(CPU& cpu, std::uint32_t mask,
                             unsigned source_destination_register) {
    if (source_destination_register >= 32u)
        return stop(cpu, StopCode::untranslated);
    if (!kb_known_cpu_program_priority(cpu))
        return stop(cpu, StopCode::undefined_process_controls);

    const std::uint32_t old_pc = cpu.process_controls;
    if (mask == 0u) {
        // Intel permits reading PC in user mode if mask is zero.
        cpu.r[source_destination_register] = old_pc;
        return true;
    }
    if (!(old_pc & KB_PC_SUPERVISOR_BIT)) {
        // This should generate architected TYPE.MISMATCH, but fault entry
        // is not implemented. Leave register and CPU state untouched.
        return stop(cpu, StopCode::modpc_type_mismatch_unimplemented);
    }
    if (mask & ~KB_PC_PRIORITY_MASK) {
        // Trace, resume, mode, state, reserved and internal fields are
        // intentionally unimplemented even if the requested value matches.
        return stop(cpu, StopCode::modpc_unsupported_fields);
    }

    const std::uint32_t requested = cpu.r[source_destination_register];
    const std::uint32_t updated = (old_pc & ~mask) | (requested & mask);
    const auto before = (old_pc & KB_PC_PRIORITY_MASK) >> 16u;
    const auto after = (updated & KB_PC_PRIORITY_MASK) >> 16u;
    if (after < before) {
        // Intel mandates checking pending interrupts before continuing.
        // Never invent an empty pending table or skip the check.
        return stop(cpu, StopCode::modpc_pending_interrupt_check_unimplemented);
    }

    cpu.process_controls = updated;
    cpu.known_process_controls = updated;
    cpu.r[source_destination_register] = old_pc;
    return true;
}
} // namespace arcaderecomp_generated
