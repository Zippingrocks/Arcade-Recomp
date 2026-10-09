// Independent Intel 80960KB interrupt-pin routing lookup.
// Source: Intel 80960KB Programmer's Reference Manual (March 1988),
// Chapter 8 pp. 8-10 to 8-11; Hardware Designer's Reference Manual.
// This is a pure decoder, NOT an interrupt scheduler, CPU exception handler
// or a model of real Sega Model 2C interrupt timing.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_generated {
enum class KBPinRole : std::uint8_t {
    direct_vector,
    iac_notification,
    external_intr,
    external_inta
};
struct KBPinRouting {
    KBPinRole role;
    std::uint8_t vector;
};
static inline KBPinRouting kb_pin_routing(std::uint32_t icr, unsigned pin) {
    if (pin >= 4u)
        throw std::out_of_range("Intel KB has exactly four interrupt pins");
    const auto number = static_cast<std::uint8_t>(icr >> (8u * pin));
    if (pin == 0u && number == 0u)
        return {KBPinRole::iac_notification, 0u};
    const auto int2 = static_cast<std::uint8_t>(icr >> 16u);
    if (int2 == 0u) {
        if (pin == 2u) return {KBPinRole::external_intr, 0u};
        if (pin == 3u) return {KBPinRole::external_inta, 0u};
    }
    return {KBPinRole::direct_vector, number};
}
static inline KBPinRouting kb_pin_routing(const CPU& cpu, unsigned pin) {
    return kb_pin_routing(cpu.interrupt_control_register, pin);
}
} // namespace arcaderecomp_generated
