// ArcadeRecomp: independently authored Intel 80960KB local-call frame runtime.
//
// Reference: Intel 80960KB Programmer's Reference Manual (1988), chapter 4
// and chapter 11 (CALL, CALLX, RET). See docs/I960_FRAMES.md.
//
// This implements normal local calls and returns only. It DOES NOT implement
// supervisor/system calls, fault and interrupt returns, trace or exact cycle
// accounting. Four register-cache slots are modeled; eviction stores all 16
// local registers through the host bus, and a returning evicted caller is read
// back. New local-register contents are *architecturally unspecified*: the
// deterministic zeros here are a research convenience, not arcade fidelity.
#pragma once
#include <cstdint>

namespace arcaderecomp_generated {

enum class StopCode : std::uint32_t {
    none = 0,
    untranslated = 1,
    frame_uninitialized = 2,
    bad_frame_pointer = 3,
    bad_instruction_pointer = 4,
    missing_bus = 5,
    unsupported_return_status = 6,
    unsupported_trace = 7,
    return_without_caller = 8,
    frame_cache_mismatch = 9,
    stack_address_wrap = 10
};

struct CPU {
    // r0-r15 are the active local window, g0-g15 occupy indices 16-31.
    // g15 (r[31]) is the global frame pointer (FP).
    std::uint32_t r[32]{};
    std::uint32_t ip = 0;
    int cc = 0;                        // Temporary compare model, NOT full AC.cc
    std::uint32_t stop_ip = 0;
    StopCode stop_code = StopCode::none;

    bool frame_initialized = false;
    std::uint32_t frame_depth = 0;
    std::uint32_t saved_local[4][16]{};
    std::uint32_t saved_fp[4]{};
    bool saved_valid[4]{};
    std::uint32_t frame_spills = 0;
    std::uint32_t frame_reloads = 0;
};

struct Bus {
    void* ctx = nullptr;
    std::uint32_t (*read32)(void*, std::uint32_t) = nullptr;
    void (*write32)(void*, std::uint32_t, std::uint32_t) = nullptr;
};

static inline bool stop(CPU& cpu, StopCode code = StopCode::untranslated) {
    cpu.stop_ip = cpu.ip;
    cpu.stop_code = code;
    return false;
}

static inline bool frame_init(CPU& cpu, std::uint32_t initial_fp,
                              std::uint32_t entry_ip) {
    if ((initial_fp & 63u) != 0u)
        return stop(cpu, StopCode::bad_frame_pointer);
    if ((entry_ip & 3u) != 0u)
        return stop(cpu, StopCode::bad_instruction_pointer);
    if (initial_fp > 0xffffffbfu)
        return stop(cpu, StopCode::stack_address_wrap);
    // Caller creates CPU{} first; zeroing uninitialized local registers is a
    // deterministic diagnostic convention and not a verified board reset.
    cpu.r[0] = 0u;
    cpu.r[1] = initial_fp + 64u;   // SP = FP + local save-area size
    cpu.r[2] = 0u;
    cpu.r[31] = initial_fp;       // global g15 = FP
    cpu.ip = entry_ip;
    cpu.frame_initialized = true;
    cpu.frame_depth = 0;
    cpu.stop_code = StopCode::none;
    for (unsigned slot = 0; slot < 4; ++slot)
        cpu.saved_valid[slot] = false;
    return true;
}

// The target and return_IP are already resolved at compile time where possible;
// CPU instructions themselves are NOT re-decoded at run time.
static inline bool frame_call(CPU& cpu, const Bus& bus,
                              std::uint32_t target, std::uint32_t return_ip) {
    if (!cpu.frame_initialized)
        return stop(cpu, StopCode::frame_uninitialized);
    if ((target & 3u) || (return_ip & 3u))
        return stop(cpu, StopCode::bad_instruction_pointer);
    if ((cpu.r[31] & 63u) != 0u)
        return stop(cpu, StopCode::bad_frame_pointer);
    const std::uint32_t sp = cpu.r[1];
    if (sp > 0xffffffbfu)
        return stop(cpu, StopCode::stack_address_wrap);
    const std::uint32_t next_fp = (sp + 63u) & ~63u;
    if (next_fp > 0xffffffbfu)
        return stop(cpu, StopCode::stack_address_wrap);
    if (cpu.frame_depth == 0xffffffffu)
        return stop(cpu, StopCode::stack_address_wrap);

    const unsigned current_slot = cpu.frame_depth & 3u;
    const unsigned next_slot = (cpu.frame_depth + 1u) & 3u;

    // On the fifth active frame, the oldest cached local set is evicted.
    if (cpu.saved_valid[next_slot]) {
        if (!bus.write32)
            return stop(cpu, StopCode::missing_bus);
        const std::uint32_t fp = cpu.saved_fp[next_slot];
        if ((fp & 63u) || fp > 0xffffffc0u)
            return stop(cpu, StopCode::bad_frame_pointer);
        for (unsigned i = 0; i < 16; ++i)
            bus.write32(bus.ctx, fp + 4u * i, cpu.saved_local[next_slot][i]);
        cpu.saved_valid[next_slot] = false;
        ++cpu.frame_spills;
    }

    // RIP lives in the *caller's* r2, not in the newly allocated frame.
    cpu.r[2] = return_ip;
    for (unsigned i = 0; i < 16; ++i)
        cpu.saved_local[current_slot][i] = cpu.r[i];
    cpu.saved_fp[current_slot] = cpu.r[31];
    cpu.saved_valid[current_slot] = true;

    // This newly allocated local window must not alias the caller's locals.
    // Intel says the initial contents of r3-r15 are unpredictable.
    for (unsigned i = 0; i < 16; ++i)
        cpu.r[i] = 0u;
    cpu.r[0] = cpu.saved_fp[current_slot]; // PFP; status bits = 000 (local)
    cpu.r[1] = next_fp + 64u;              // SP
    cpu.r[31] = next_fp;                  // FP in global g15
    ++cpu.frame_depth;
    cpu.ip = target;
    return true;
}

static inline bool frame_return(CPU& cpu, const Bus& bus) {
    if (!cpu.frame_initialized)
        return stop(cpu, StopCode::frame_uninitialized);
    if (cpu.frame_depth == 0u)
        return stop(cpu, StopCode::return_without_caller);
    const std::uint32_t return_status = cpu.r[0] & 7u;
    if (return_status != 0u)
        return stop(cpu, StopCode::unsupported_return_status);
    // Prereturn trace may have architectural side effects we do not model.
    if (cpu.r[0] & 8u)
        return stop(cpu, StopCode::unsupported_trace);
    const std::uint32_t previous_fp = cpu.r[0] & ~63u;
    const unsigned previous_slot = (cpu.frame_depth - 1u) & 3u;
    const unsigned departing_slot = cpu.frame_depth & 3u;
    std::uint32_t restored[16]{};

    if (cpu.saved_valid[previous_slot]) {
        if (cpu.saved_fp[previous_slot] != previous_fp)
            return stop(cpu, StopCode::frame_cache_mismatch);
        for (unsigned i = 0; i < 16; ++i)
            restored[i] = cpu.saved_local[previous_slot][i];
    } else {
        if (!bus.read32)
            return stop(cpu, StopCode::missing_bus);
        if (previous_fp > 0xffffffc0u)
            return stop(cpu, StopCode::bad_frame_pointer);
        for (unsigned i = 0; i < 16; ++i)
            restored[i] = bus.read32(bus.ctx, previous_fp + 4u * i);
        ++cpu.frame_reloads;
    }

    cpu.saved_valid[departing_slot] = false;
    cpu.saved_valid[previous_slot] = false; // becomes the active local window
    --cpu.frame_depth;
    for (unsigned i = 0; i < 16; ++i)
        cpu.r[i] = restored[i];
    cpu.r[31] = previous_fp;
    cpu.ip = cpu.r[2]; // caller's saved RIP (instruction after original CALL)
    if (cpu.ip & 3u)
        return stop(cpu, StopCode::bad_instruction_pointer);
    return true;
}

} // namespace arcaderecomp_generated
