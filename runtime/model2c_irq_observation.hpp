// ArcadeRecomp: independent, read-only Model 2C -> Intel 80960KB IRQ snapshot.
//
// This joins the existing *provisional* Sega request/pin grouping with
// Intel's documented ICR pin-role decoder. It NEVER arbitrates simultaneous
// pins, accepts an interrupt, changes CPU registers or executes an IRQ frame.
// No source event is invented; clients must provide an explicitly configured
// PartialIRQRegisters test/research source.
#pragma once

#include "i960_interrupt_pins.hpp"
#include "model2c_irq_registers.hpp"

#include <array>
#include <cstdint>

namespace arcaderecomp_model2c {

struct Model2CPinObservation {
    bool asserted = false;
    std::uint32_t requested_source_bits = 0u;
    arcaderecomp_generated::KBPinRole role =
        arcaderecomp_generated::KBPinRole::direct_vector;
    std::uint8_t configured_vector = 0u;
    // A direct vector configured in the ICR is still only a *candidate*.
    // This bit NEVER means the i960 accepted or serviced an IRQ.
    bool direct_vector_candidate = false;
};

struct Model2CIRQObservation {
    std::uint32_t request_register = 0u;
    std::uint32_t enabled_register = 0u;
    unsigned queued_enable_cycles = 0u;
    std::uint32_t intel_icr = 0u;
    std::array<Model2CPinObservation, 4> pins{};
    unsigned asserted_line_count = 0u;
    unsigned direct_candidate_count = 0u;
    unsigned unresolved_non_vector_count = 0u;

    // This API has no vector-accept/priority result by design.
    // In particular, a uniquely asserted pin is not a verified IRQ entry.
};

// Pure observation only; no time advances, no pending bits are consumed.
// Unlike a real board or CPU, this function has no IRQ event scheduler.
inline Model2CIRQObservation observe_model2c_irq(
    const PartialIRQRegisters& board,
    const arcaderecomp_generated::CPU& cpu) {
    Model2CIRQObservation snapshot{};
    snapshot.request_register = board.request();
    snapshot.enabled_register = board.enable();
    snapshot.queued_enable_cycles = board.pending_enable_cycles();
    snapshot.intel_icr = cpu.interrupt_control_register;
    for (unsigned pin = 0; pin < snapshot.pins.size(); ++pin) {
        auto& observed = snapshot.pins[pin];
        observed.requested_source_bits =
            snapshot.request_register & PartialIRQRegisters::pin_source_mask(pin);
        observed.asserted = observed.requested_source_bits != 0u;
        const auto routing = arcaderecomp_generated::kb_pin_routing(cpu, pin);
        observed.role = routing.role;
        observed.configured_vector = routing.vector;
        observed.direct_vector_candidate =
            observed.asserted &&
            routing.role == arcaderecomp_generated::KBPinRole::direct_vector;
        if (observed.asserted) {
            ++snapshot.asserted_line_count;
            if (observed.direct_vector_candidate)
                ++snapshot.direct_candidate_count;
            else
                ++snapshot.unresolved_non_vector_count;
        }
    }
    return snapshot;
}
} // namespace arcaderecomp_model2c
