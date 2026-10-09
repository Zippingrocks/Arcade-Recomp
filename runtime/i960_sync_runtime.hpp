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

#include <array>
#include <cstdint>

namespace arcaderecomp_generated {

static constexpr std::uint32_t I960_LOCAL_IAC = 0xff000010u;
static constexpr std::uint32_t I960_IAC_REINITIALIZE = 0x93u;

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
