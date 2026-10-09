// ArcadeRecomp: independently authored Intel 80960KB SYNMOVQ boundary.
// Primary reference: Intel 80960KB Programmer's Reference Manual (1988),
// chapter 11 pages 11-126..11-128, chapter 13 page 13-10.
//
// SYNMOVQ with destination 0xff000010 submits a four-word IAC message to
// the local processor. Message 0x93 requests processor reinitialization.
// This module VALIDATES AND CAPTURES that message but deliberately halts
// before changing SAT/PRCB/IP: the full reset/interrupt-stack transition is
// not yet independently implemented. No guessed 0x93 side effects.
#pragma once
#include "i960_frame_runtime.hpp"
#include "i960_reinitialize.hpp"

#include <array>
#include <cstdint>

namespace arcaderecomp_generated {

static constexpr std::uint32_t I960_LOCAL_IAC = 0xff000010u;
static constexpr std::uint32_t I960_IAC_REINITIALIZE = 0x93u;

static constexpr std::uint32_t I960_LOCAL_ICR = 0xff000004u;

// Intel 80960KB SYNMOV transfers one word from [src] to [dst], waits for
// synchronous completion, and sets AC.cc to 0b010 on success. The on-chip
// interrupt-control register is a documented special destination at
// 0xFF000004. No ordinary peripheral writes are modeled as successful here.
static inline bool sync_move_word(CPU& cpu, const Bus& bus,
                                  std::uint32_t destination,
                                  std::uint32_t source) {
    const std::uint32_t aligned_dst = destination & ~3u;
    const std::uint32_t aligned_src = source & ~3u;
    if (aligned_dst != I960_LOCAL_ICR)
        return stop(cpu, StopCode::synchronous_device_unimplemented);
    if (!bus.read32)
        return stop(cpu, StopCode::missing_bus);
    // Resolve source before modifying the CPU; an unmapped read must not
    // make the interrupt register appear to have been updated.
    const std::uint32_t value = bus.read32(bus.ctx, aligned_src);
    cpu.interrupt_control_register = value;
    cpu.cc = 2;
    cpu.cc_defined = true;
    return true;
}


// Intel 80960KB manual, p. 11-124: SYNLD src,dst reads one word from
// [src-register] into dst-register. Internal ICR is always readable.
// For other addresses, a separate completion callback is mandatory.
// A Bad Access sets AC.cc=000 without a CPU fault; dst stays unchanged.
static inline bool sync_load_word(CPU& cpu, const Bus& bus,
                                  std::uint32_t src_address,
                                  unsigned dst_register) {
    if (dst_register >= 32u)
        return stop(cpu, StopCode::untranslated);
    const std::uint32_t address = src_address & ~3u;
    if (address == I960_LOCAL_ICR) {
        cpu.r[dst_register] = cpu.interrupt_control_register;
        cpu.cc = 2;
        cpu.cc_defined = true;
        return true;
    }
    if (!bus.read32_sync)
        return stop(cpu, StopCode::synchronous_device_unimplemented);
    std::uint32_t result = 0;
    const bool success = bus.read32_sync(bus.ctx, address, &result);
    if (success) cpu.r[dst_register] = result;
    cpu.cc = success ? 2 : 0;
    cpu.cc_defined = true;
    return true;
}

static inline bool sync_move_quad(CPU& cpu, const Bus& bus,
                                  std::uint32_t destination,
                                  std::uint32_t source) {
    if (!bus.read32)
        return stop(cpu, StopCode::missing_bus);

    // The 80960KB forces a 16-byte boundary for the quad operation.
    const std::uint32_t aligned_source = source & ~15u;
    const std::uint32_t aligned_destination = destination & ~15u;

    // Read the complete message first. If a mapped-bus fault occurs, we do
    // not mutate the CPU's pending message state or invent a transaction.
    std::array<std::uint32_t, 4> words{};
    for (unsigned index = 0; index != 4; ++index)
        words[index] = bus.read32(bus.ctx, aligned_source + 4u * index);

    if (aligned_destination == I960_LOCAL_IAC) {
        for (unsigned index = 0; index != 4; ++index)
            cpu.pending_iac[index] = words[index];
        cpu.pending_iac_valid = true;
        if ((words[0] >> 24) == I960_IAC_REINITIALIZE) {
            // 0x93 uses: SAT=field3, PRCB=field4, new IP=field5.
            // Verify alignment before advertising a decoded reinit request.
            if ((words[1] & 3u) || (words[2] & 3u) || (words[3] & 3u))
                return stop(cpu, StopCode::bad_instruction_pointer);
            if (cpu.allow_iac_93_reinitialize)
                return perform_iac_93_reinitialize(cpu, bus);
            return stop(cpu, StopCode::iac_reinitialize_pending);
        }
        return stop(cpu, StopCode::unsupported_iac_message);
    }

    // Device-completion and noncacheable synchronous write semantics must
    // be provided by a specifically modeled transaction backend. Ordinary
    // 32-bit memory writes are NOT an acceptable substitute for SYNMOVQ.
    return stop(cpu, StopCode::synchronous_device_unimplemented);
}

} // namespace arcaderecomp_generated
