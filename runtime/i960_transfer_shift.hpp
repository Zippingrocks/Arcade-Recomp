// Original ArcadeRecomp implementation from Intel 80960KB PRM (1988):
// load 11-67, move 11-85, shifts 11-110/111, store 11-117; literals 5-10.
// Functional instruction semantics, not timing or precise hardware faults.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {

// Register groups must stay within one local/global bank. Intel marks
// invalid or overlapping multi-register moves unpredictable: refuse them.
static inline bool valid_group(unsigned first, unsigned count) {
    const unsigned alignment = count == 2 ? 2u : 4u;
    return count >= 2u && count <= 4u && first < 32u &&
           (first % alignment) == 0u && (first % 16u) + count <= 16u;
}
static inline bool transfer_load(CPU& cpu, const Bus& bus,
                                 std::uint32_t address, unsigned first,
                                 unsigned count) {
    if (!valid_group(first, count)) return stop(cpu, StopCode::untranslated);
    if (!bus.read32) return stop(cpu, StopCode::missing_bus);
    // Address captured by value before destinations overwrite any base/index.
    // Do not force 8/16-byte memory alignment: ordinary multiword loads may
    // start at any supported word address. Bus handles unsupported alignment.
    std::uint32_t values[4]{};
    for (unsigned n = 0; n < count; ++n)
        values[n] = bus.read32(bus.ctx, address + 4u * n);
    for (unsigned n = 0; n < count; ++n) cpu.r[first + n] = values[n];
    // If a diagnostic bus read throws, destination registers are untouched.
    // This is diagnostic safety, NOT precise 80960KB fault rollback semantics.
    return true;
}
static inline bool transfer_store(CPU& cpu, const Bus& bus,
                                  std::uint32_t address, unsigned first,
                                  unsigned count) {
    if (!valid_group(first, count)) return stop(cpu, StopCode::untranslated);
    if (!bus.write32) return stop(cpu, StopCode::missing_bus);
    std::uint32_t values[4]{};
    for (unsigned n = 0; n < count; ++n) values[n] = cpu.r[first + n];
    for (unsigned n = 0; n < count; ++n)
        bus.write32(bus.ctx, address + 4u * n, values[n]);
    // Partial external writes cannot be rolled back if a later bus access
    // throws. A stopped diagnostic must not be resumed as an atomic retry.
    return true;
}
static inline bool transfer_move(CPU& cpu, unsigned source, unsigned first,
                                 unsigned count, bool literal) {
    if (!valid_group(first, count)) return stop(cpu, StopCode::untranslated);
    if (literal) {
        if (source > 31u) return stop(cpu, StopCode::untranslated);
        cpu.r[first] = source;
        for (unsigned n = 1; n < count; ++n) cpu.r[first+n] = 0;
        return true;
    }
    if (!valid_group(source, count)) return stop(cpu, StopCode::untranslated);
    if (source < first + count && first < source + count)
        return stop(cpu, StopCode::untranslated); // PRM: unpredictable overlap
    for (unsigned n = 0; n < count; ++n) cpu.r[first+n] = cpu.r[source+n];
    return true;
}

// Never inherit the host CPU's masked shift count. Intel KB logical shifts
// by >=32 yield zero; SHRI yields sign fill; SHRDI truncates toward zero.
static inline std::uint32_t kb_shlo(std::uint32_t count, std::uint32_t value) {
    return count >= 32u ? 0u : value << count;
}
static inline std::uint32_t kb_shro(std::uint32_t count, std::uint32_t value) {
    return count >= 32u ? 0u : value >> count;
}
static inline std::uint32_t kb_shri(std::uint32_t count, std::uint32_t value) {
    const bool negative = (value & 0x80000000u) != 0;
    if (count >= 32u) return negative ? 0xffffffffu : 0u;
    if (count == 0u) return value;
    const std::uint32_t result = value >> count;
    return negative ? result | (0xffffffffu << (32u-count)) : result;
}
static inline std::uint32_t kb_shrdi(std::uint32_t count, std::uint32_t value) {
    if (count >= 32u) return 0u;
    if (count == 0u) return value;
    const bool negative = (value & 0x80000000u) != 0;
    const std::uint32_t magnitude = negative ? 0u-value : value;
    const std::uint32_t result = magnitude >> count;
    return negative ? 0u-result : result;
}
} // namespace arcaderecomp_generated
