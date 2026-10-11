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
    stack_address_wrap = 10,
    iac_reinitialize_pending = 11,
    unsupported_iac_message = 12,
    synchronous_device_unimplemented = 13,
    iac_bad_message = 14,
    iac_invalid_prcb = 15,
    undefined_condition_code = 16,
    undefined_integer_controls = 17,
    integer_overflow_pending = 18,
    undefined_floating_point_register = 19,
    unsupported_floating_rounding = 20,
    unsupported_floating_format = 21,
    unsupported_floating_integer_range = 22,
    unsupported_floating_division_fault = 23,
    undefined_process_controls = 24,
    modpc_type_mismatch_unimplemented = 25,
    modpc_pending_interrupt_check_unimplemented = 26,
    modpc_unsupported_fields = 27
};

// A diagnostic handoff, not an architected in-memory fault record.
struct PendingIntegerOverflow {
    bool pending = false;
    std::uint32_t instruction_ip = 0;
    std::uint32_t resume_ip = 0;
};

// 80960KB's 80-bit FP payload. Keep the exact original bit pattern rather
// than passing through host long double (whose representation is not portable).
struct ExtendedReal {
    std::uint32_t low = 0;
    std::uint32_t middle = 0;
    std::uint16_t high = 0;
};

struct CPU {
    // r0-r15 are the active local window, g0-g15 occupy indices 16-31.
    // g15 (r[31]) is the global frame pointer (FP).
    std::uint32_t r[32]{};
    // Four physical 80-bit floating registers; contents after reset are
    // unknown until written by an independently supported instruction.
    ExtendedReal fp[4]{};
    bool fp_defined[4]{};
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
    std::uint32_t pending_iac[4]{};
    bool pending_iac_valid = false;
    // Reinitialize is explicitly opt-in until complete CPU/I/O hardware
    // validation. Strict original-ROM runs retain their existing stop.
    bool allow_iac_93_reinitialize = false;
    std::uint32_t sat_address = 0;
    std::uint32_t prcb_address = 0;
    std::uint32_t interrupt_table_address = 0;
    std::uint32_t interrupt_stack_address = 0;
    std::uint32_t fault_table_address = 0;
    std::uint32_t process_controls = 0;
    // Unknown by default. A successfully validated opt-in IAC 0x93
    // establishes an initial priority-31 value, but a raw zero-initialized
    // CPU or user-edited process-controls word proves no CPU priority.
    bool process_controls_priority_known = false;
    std::uint32_t known_process_controls = 0;
    std::uint32_t trace_controls = 0;
    // Intel 80960KB internal interrupt-pin vector routing (synmov/synld
    // at 0xFF000004). Initialized to FF000000h by processor reset.
    std::uint32_t interrupt_control_register = 0xff000000u;
    bool cc_defined = true;  // Set false by i960KB reinitialization.
    // AC[12] mask and sticky AC[8] flag. Intel reset/reinitialize leave AC
    // undefined: do not silently choose masked or trapping overflow behavior.
    bool integer_overflow_mask = false;
    bool integer_overflow_mask_defined = false;
    bool integer_overflow_flag = false;
    bool integer_overflow_flag_defined = false;
    PendingIntegerOverflow pending_integer_overflow{};
    bool prcb_loaded = false;
    std::uint32_t reinitialize_count = 0;
};

struct Bus {
    void* ctx = nullptr;
    std::uint32_t (*read32)(void*, std::uint32_t) = nullptr;
    void (*write32)(void*, std::uint32_t, std::uint32_t) = nullptr;
    // Independent width-specific callbacks preserve byte-lane I/O semantics.
    // Device backends must refuse unmapped or unsupported accesses rather
    // than silently treating control registers like ordinary RAM.
    std::uint8_t (*read8)(void*, std::uint32_t) = nullptr;
    void (*write8)(void*, std::uint32_t, std::uint8_t) = nullptr;
    std::uint16_t (*read16)(void*, std::uint32_t) = nullptr;
    void (*write16)(void*, std::uint32_t, std::uint16_t) = nullptr;
    // Explicitly completed 32-bit synchronous read. False denotes hardware
    // Bad Access without raising an i960 CPU exception or mutating dst.
    // Async read32 MUST NOT silently stand in for a peripheral transaction.
    bool (*read32_sync)(void*, std::uint32_t, std::uint32_t*) = nullptr;
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
    cpu.interrupt_control_register = 0xff000000u;
    // frame_init is also used for initial/test frames: do not confuse this
    // with successful Intel PRCB reinitialization or an established priority.
    cpu.process_controls_priority_known = false;
    cpu.known_process_controls = 0u;
    cpu.integer_overflow_mask_defined = false;
    cpu.integer_overflow_flag_defined = false;
    cpu.pending_integer_overflow = {};
    for (unsigned slot = 0; slot < 4; ++slot) {
        cpu.saved_valid[slot] = false;
        cpu.fp_defined[slot] = false;  // Reset does not invent FP values.
    }
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

// FLUSHREG (Intel 80960KB, 66Dh): write each cached inactive local
// register set to its stack frame, then invalidate those cache entries.
// The *active* r[0..15] set must remain live and must NOT be stored.
// The current Bus write callback cannot report mid-transfer bus faults;
// exact exception/interrupt restart timing remains unimplemented.
static inline bool frame_flush(CPU& cpu, const Bus& bus) {
    if (!cpu.frame_initialized)
        return stop(cpu, StopCode::frame_uninitialized);

    // Validate all pending stores first; do not cause partial writes for
    // invalid internal frame metadata or missing write callbacks.
    bool any = false;
    for (unsigned slot = 0; slot < 4; ++slot) {
        if (!cpu.saved_valid[slot])
            continue;
        any = true;
        const std::uint32_t fp = cpu.saved_fp[slot];
        if ((fp & 63u) != 0u || fp > 0xffffffc0u)
            return stop(cpu, StopCode::bad_frame_pointer);
    }
    if (any && !bus.write32)
        return stop(cpu, StopCode::missing_bus);

    for (unsigned slot = 0; slot < 4; ++slot) {
        if (!cpu.saved_valid[slot])
            continue;
        const std::uint32_t fp = cpu.saved_fp[slot];
        for (unsigned i = 0; i < 16; ++i)
            bus.write32(bus.ctx, fp + 4u * i, cpu.saved_local[slot][i]);
        cpu.saved_valid[slot] = false;
        ++cpu.frame_spills;
    }
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
    bool needs_reload = false;

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
        needs_reload = true;
    }

    // This is an explicit diagnostic stop, NOT implemented Intel fault
    // delivery. Validate the restored caller RIP *before* invalidating
    // cached frames or changing IP/SP/FP/register windows. Previously a
    // malformed RIP corrupted the live frame and blamed the wrong stop IP.
    if ((restored[2] & 3u) != 0u)
        return stop(cpu, StopCode::bad_instruction_pointer);
    if (needs_reload) ++cpu.frame_reloads;

    cpu.saved_valid[departing_slot] = false;
    cpu.saved_valid[previous_slot] = false; // becomes the active local window
    --cpu.frame_depth;
    for (unsigned i = 0; i < 16; ++i)
        cpu.r[i] = restored[i];
    cpu.r[31] = previous_fp;
    cpu.ip = restored[2]; // caller's saved RIP (checked above)
    return true;
}

} // namespace arcaderecomp_generated
