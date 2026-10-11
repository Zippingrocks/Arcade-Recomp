// ArcadeRecomp: independent, read-only Model 2C -> Intel 80960KB IRQ snapshot.
//
// This joins the existing *provisional* Sega request/pin grouping with
// Intel's documented ICR pin-role decoder. It NEVER arbitrates simultaneous
// pins, accepts an interrupt, changes CPU registers or executes an IRQ frame.
// No source event is invented; clients must provide an explicitly configured
// PartialIRQRegisters test/research source.
#pragma once

#include "i960_interrupt_pins.hpp"
#include "i960_interrupt_priority.hpp"
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
// Optional *second* observation pass. The Intel current program priority is
// not presently independently decoded from this project's CPU process
// controls, so it must be supplied explicitly by the research caller.
// Do NOT use this information to accept, arbitrate, or deliver interrupts.
struct Model2CPinPriorityReview {
    bool evaluated = false; // false for unasserted pins or IAC/INTR/INTA
    arcaderecomp_generated::KBVectorPriorityReview vector{};
};
struct Model2CIRQPriorityReview {
    unsigned externally_supplied_current_priority = 0u;
    std::array<Model2CPinPriorityReview, 4> pins{};
    unsigned higher_priority_candidates = 0u;
    unsigned would_post_pending = 0u;
    unsigned invalid_or_reserved_vectors = 0u;
    unsigned non_direct_asserted_pins = 0u;
};

// Read-only interpretation of a frozen board/ICR snapshot. This neither
// selects a highest priority pin nor models the required pending table,
// priority mutation, edge semantics, interrupt frame or board ACK.
inline Model2CIRQPriorityReview review_model2c_irq_priorities(
    const Model2CIRQObservation& snapshot, unsigned current_priority) {
    if (current_priority > 31u)
        throw std::out_of_range("Intel program priority outside 0..31");
    Model2CIRQPriorityReview review{};
    review.externally_supplied_current_priority = current_priority;
    for (unsigned pin = 0; pin < review.pins.size(); ++pin) {
        const auto& observed = snapshot.pins[pin];
        if (!observed.asserted) continue;
        if (!observed.direct_vector_candidate) {
            ++review.non_direct_asserted_pins;
            continue;
        }
        auto& result = review.pins[pin];
        result.evaluated = true;
        result.vector = arcaderecomp_generated::review_kb_vector_priority(
            observed.configured_vector, current_priority);
        using arcaderecomp_generated::KBVectorDisposition;
        switch (result.vector.disposition) {
        case KBVectorDisposition::higher_priority_candidate:
            ++review.higher_priority_candidates;
            break;
        case KBVectorDisposition::would_post_pending:
            ++review.would_post_pending;
            break;
        case KBVectorDisposition::invalid_vector:
        case KBVectorDisposition::reserved_vector:
            ++review.invalid_or_reserved_vectors;
            break;
        }
    }
    return review;
}

} // namespace arcaderecomp_model2c
