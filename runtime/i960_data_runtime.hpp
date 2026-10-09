// Independent Intel 80960KB data-movement and shift semantics.
// Intel KB manual (1988): pp. 3-5, 11-67, 11-85, 11-110, 11-117.
// This is functional CPU semantics, NOT cycle/exception/scoreboard fidelity.
#pragma once
#include "i960_frame_runtime.hpp"
#include <array>
#include <cstdint>

namespace arcaderecomp_generated {
constexpr bool valid_data_group(unsigned first, unsigned count) {
    return count >= 2u && count <= 4u && first < 32u &&
        first % (count == 2u ? 2u : 4u) == 0u &&
        (first % 16u) + count <= 16u;
}

template<unsigned Count>
static inline bool load_group(CPU& cpu, const Bus& bus,
                              std::uint32_t address, unsigned destination) {
    static_assert(Count >= 2u && Count <= 4u);
    if (!valid_data_group(destination, Count))
        return stop(cpu, StopCode::undefined_register_group);
    if (!bus.read_words) return stop(cpu, StopCode::missing_bus);
    // Address is evaluated before dst writes (base/index may alias dst).
    // No partial register update on an unavailable/invalid memory span.
    std::array<std::uint32_t, Count> values{};
    if (!bus.read_words(bus.ctx, address, values.data(), Count))
        return stop(cpu, StopCode::unsupported_block_transfer);
    for (unsigned i = 0; i < Count; ++i) cpu.r[destination + i] = values[i];
    return true;
}

template<unsigned Count>
static inline bool store_group(CPU& cpu, const Bus& bus,
                               std::uint32_t address, unsigned source) {
    static_assert(Count >= 2u && Count <= 4u);
    if (!valid_data_group(source, Count))
        return stop(cpu, StopCode::undefined_register_group);
    if (!bus.write_words) return stop(cpu, StopCode::missing_bus);
    std::array<std::uint32_t, Count> values{};
    for (unsigned i = 0; i < Count; ++i) values[i] = cpu.r[source + i];
    if (!bus.write_words(bus.ctx, address, values.data(), Count))
        return stop(cpu, StopCode::unsupported_block_transfer);
    return true;
}

template<unsigned Count>
static inline bool move_group(CPU& cpu, unsigned source, unsigned destination) {
    static_assert(Count >= 2u && Count <= 4u);
    if (!valid_data_group(source, Count) || !valid_data_group(destination, Count))
        return stop(cpu, StopCode::undefined_register_group);
    // KB manual explicitly calls overlapping MOVL/MOVT/MOVQ unpredictable.
    // Do not silently choose host memmove semantics, including src==dst.
    if (source < destination + Count && destination < source + Count)
        return stop(cpu, StopCode::undefined_register_group);
    for (unsigned i = 0; i < Count; ++i) cpu.r[destination + i] = cpu.r[source + i];
    return true;
}

constexpr std::uint32_t shift_left_ordinal(std::uint32_t value, std::uint32_t count) {
    return count < 32u ? (value << count) : 0u;
}
constexpr std::uint32_t shift_right_ordinal(std::uint32_t value, std::uint32_t count) {
    return count < 32u ? (value >> count) : 0u;
}
constexpr std::uint32_t shift_right_integer(std::uint32_t value, std::uint32_t count) {
    const bool negative = (value & 0x80000000u) != 0u;
    if (!count) return value;
    if (count >= 32u) return negative ? 0xffffffffu : 0u;
    return (value >> count) | (negative ? (0xffffffffu << (32u - count)) : 0u);
}
constexpr std::uint32_t shift_right_dividing(std::uint32_t value, std::uint32_t count) {
    if (!count) return value;
    if (count >= 32u) return 0u;
    const bool negative = (value & 0x80000000u) != 0u;
    const std::uint32_t magnitude = negative ? (0u - value) : value;
    const auto quotient = magnitude >> count;
    return negative ? (0u - quotient) : quotient;
}
} // namespace arcaderecomp_generated
