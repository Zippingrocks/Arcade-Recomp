// ArcadeRecomp: partial, opt-in Intel 80960KB Reinitialize Processor IAC.
//
// Authoritative reference: Intel 80960KB Programmer's Reference Manual
// (March 1988), ch. 7 pp. 7-10 through 7-15 and ch. 13 p. 13-10.
//
// Reads an IAC 0x93 request, resolves the RAM-resident PRCB fields via the
// CPU memory bus, installs a new startup frame, and transfers to the IAC IP.
// This is intentionally NOT a complete i960KB processor reset: externally
// latched interrupts, instruction-cache timing, and undefined register values
// remain to be verified. It is OPT-IN and OFF by default on the real-ROM probe.
#pragma once
#include "i960_frame_runtime.hpp"

#include <cstdint>

namespace arcaderecomp_generated {

struct KBReinitializeSnapshot {
    std::uint32_t sat = 0;
    std::uint32_t prcb = 0;
    std::uint32_t ip = 0;
    std::uint32_t flags = 0;           // PRCB +4, hardware meaning pending
    std::uint32_t interrupt_table = 0; // PRCB +20
    std::uint32_t interrupt_stack = 0; // PRCB +24
    std::uint32_t magic_a = 0;         // PRCB +32
    std::uint32_t magic_b = 0;         // PRCB +36
    std::uint32_t fault_table = 0;     // PRCB +40
    std::uint32_t reserved_44 = 0;     // PRCB +44
};

// Intel KB reinitialization is an IAC operation; it does not advance
// past the original SYNMOVQ. The bus has to provide readable PRCB memory.
// Validation and all memory reads happen BEFORE any CPU state mutation.
static inline bool perform_iac_93_reinitialize(CPU& cpu, const Bus& bus) {
    if (!cpu.pending_iac_valid ||
        (cpu.pending_iac[0] >> 24) != 0x93u)
        return stop(cpu, StopCode::iac_bad_message);
    if (!bus.read32)
        return stop(cpu, StopCode::missing_bus);

    KBReinitializeSnapshot next{};
    next.sat = cpu.pending_iac[1];
    next.prcb = cpu.pending_iac[2];
    next.ip = cpu.pending_iac[3];
    if ((next.sat & 3u) || (next.prcb & 3u) || (next.ip & 3u) ||
        next.prcb > 0xffffffcfu)
        return stop(cpu, StopCode::iac_invalid_prcb);

    // The 80960KB initial-memory-image PRCB describes the interrupt table,
    // initial interrupt stack, and fault-table address at these offsets.
    // Capture additional PRCB fields for inspection rather than hard-coding
    // revision-dependent magic values. The original HOTD1 PRCB includes
    // 0x1ff at +32 even though the 1988 Intel document lists 0x27f there.
    next.flags = bus.read32(bus.ctx, next.prcb + 4u);
    next.interrupt_table = bus.read32(bus.ctx, next.prcb + 20u);
    next.interrupt_stack = bus.read32(bus.ctx, next.prcb + 24u);
    next.magic_a = bus.read32(bus.ctx, next.prcb + 32u);
    next.magic_b = bus.read32(bus.ctx, next.prcb + 36u);
    next.fault_table = bus.read32(bus.ctx, next.prcb + 40u);
    next.reserved_44 = bus.read32(bus.ctx, next.prcb + 44u);
    if ((next.interrupt_stack & 63u) ||
        next.interrupt_stack > 0xffffffbfu ||
        (next.interrupt_table & 3u) || (next.fault_table & 3u))
        return stop(cpu, StopCode::iac_invalid_prcb);

    // Do not expose a successful transition until all prerequisites above
    // passed. Registers r3-r15 and g0-g14 have unspecified reset contents
    // in our currently modeled processor: their retained host values are a
    // research convention, NOT a measured real-board result.
    if (!frame_init(cpu, next.interrupt_stack, next.ip))
        return false;
    cpu.sat_address = next.sat;
    cpu.prcb_address = next.prcb;
    cpu.interrupt_table_address = next.interrupt_table;
    cpu.interrupt_stack_address = next.interrupt_stack;
    cpu.fault_table_address = next.fault_table;
    cpu.prcb_loaded = true;

    // Initial state: priority 31 (bits 16..20), interrupted (bit 13),
    // supervisor execution (bit 1). Trace state is initialized to zero.
    cpu.process_controls = (31u << 16) | (1u << 13) | (1u << 1);
    cpu.trace_controls = 0;
    // AC is architecturally undefined on KB reinitialization. Do NOT
    // allow a stale pre-reinitialization CC to determine a later branch.
    cpu.cc = 0;
    cpu.cc_defined = false;
    cpu.pending_iac_valid = false;
    ++cpu.reinitialize_count;
    cpu.stop_ip = 0;
    cpu.stop_code = StopCode::none;
    return true;
}

} // namespace arcaderecomp_generated
