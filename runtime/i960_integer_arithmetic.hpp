// Original ArcadeRecomp Intel 80960KB ADDI/SUBI semantics.
// Intel 270567-001 (1988): 3-7, 3-9/10, 9-16, 11-7, 11-120.
// Full trap delivery and AC load/store instructions are NOT implemented here.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

static inline bool stop_pending_integer_overflow(CPU& cpu) {
    cpu.stop_ip = cpu.pending_integer_overflow.instruction_ip;
    cpu.stop_code = StopCode::integer_overflow_pending;
    return false;
}

// The caller must obtain these two bits from a verified saved AC value or an
// explicit fixture. This is not a guessed CPU reset value or a guest MODAC.
static inline void establish_integer_controls(CPU& cpu, std::uint32_t ac) {
    cpu.integer_overflow_mask = (ac & 0x1000u) != 0;
    cpu.integer_overflow_mask_defined = true;
    cpu.integer_overflow_flag = (ac & 0x100u) != 0;
    cpu.integer_overflow_flag_defined = true;
}

static inline bool integer_add_sub(CPU& cpu, std::uint32_t src1,
                                   std::uint32_t src2, unsigned destination,
                                   std::uint32_t next_ip, bool subtract) {
    if (cpu.pending_integer_overflow.pending)
        return stop_pending_integer_overflow(cpu);
    if (destination >= 32u)
        return stop(cpu, StopCode::untranslated);
    if (next_ip & 3u)
        return stop(cpu, StopCode::bad_instruction_pointer);

    // All host calculations are unsigned. The sign-bit formula detects signed
    // overflow without C++ signed overflow or implementation-defined casts.
    const std::uint32_t result = subtract ? src2 - src1 : src2 + src1;
    const bool overflow = ((subtract ? (src2 ^ src1) : ~(src2 ^ src1)) &
                           (src2 ^ result) & 0x80000000u) != 0;
    if (overflow && !cpu.integer_overflow_mask_defined)
        return stop(cpu, StopCode::undefined_integer_controls);

    cpu.r[destination] = result;
    if (overflow) {
        if (cpu.integer_overflow_mask) {
            // Masked overflow sets the sticky AC[8]. Non-overflow operations
            // do not clear it. ADDI/SUBI do not modify the compare flags.
            cpu.integer_overflow_flag = true;
            cpu.integer_overflow_flag_defined = true;
        } else {
            // Intel specifies a post-result fault: destination is already
            // written, AC[8] is NOT set, and saved return IP is the next IP.
            // Keep a pending diagnostic handoff; never execute the instruction
            // again or pretend that a fault handler has run successfully.
            cpu.pending_integer_overflow = {true, cpu.ip, next_ip};
            return stop_pending_integer_overflow(cpu);
        }
    }
    return true;
}
} // namespace arcaderecomp_generated
