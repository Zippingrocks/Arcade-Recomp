// Intel 80960KB interrupt-vector *priority classification* only.
// Independently implemented from Intel 80960KB Programmer's Reference Manual
// (March 1988), Chapter 8 pp. 8-2, 8-3, 8-8 and 8-9.
//
// This does not sample interrupt pins, inspect CPU process-controls bits,
// maintain pending memory, arbitrate delivery, enter supervisor mode, or
// construct an interrupt frame. The caller MUST supply current priority
// explicitly from independently verified state, not infer it from ICR.
#pragma once

#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_generated {

enum class KBVectorDisposition : std::uint8_t {
    invalid_vector,   // vectors 0..7 or numbers beyond the 8-bit range
    reserved_vector,  // vectors 244..251 are Intel-reserved
    would_post_pending,
    higher_priority_candidate
};

struct KBVectorPriorityReview {
    KBVectorDisposition disposition = KBVectorDisposition::invalid_vector;
    unsigned vector = 0u;
    unsigned vector_priority = 0u;
    // Offsets into Intel's architected interrupt table. These are metadata,
    // not actual memory accesses or a successful posted/serviced interrupt.
    unsigned handler_offset = 0u;
    unsigned pending_vector_byte_offset = 0u;
    std::uint8_t pending_vector_bit = 0u;
    std::uint32_t pending_priority_bit = 0u;
};

// current_priority in 0..31 is an explicit *research input*. Do not feed a
// guessed CPU priority here. Intel specifies vector priority = vector / 8.
// Vectors 0..7 are invalid and 244..251 reserved. Priority 31 is always
// immediately serviceable even at a current priority of 31.
// "candidate" does NOT mean the processor accepted or delivered an IRQ.
inline KBVectorPriorityReview review_kb_vector_priority(
    unsigned vector, unsigned current_priority) {
    if (current_priority > 31u)
        throw std::out_of_range("Intel 80960KB program priority outside 0..31");
    KBVectorPriorityReview result{};
    result.vector = vector;
    if (vector < 8u || vector > 255u)
        return result;
    if (vector >= 244u && vector <= 251u) {
        result.disposition = KBVectorDisposition::reserved_vector;
        return result;
    }
    result.vector_priority = vector / 8u;
    result.handler_offset = (vector + 1u) * 4u;
    result.pending_vector_byte_offset = 4u + vector / 8u;
    result.pending_vector_bit =
        static_cast<std::uint8_t>(1u << (vector & 7u));
    result.pending_priority_bit = std::uint32_t{1u} << result.vector_priority;
    result.disposition = (result.vector_priority == 31u ||
                          result.vector_priority > current_priority)
        ? KBVectorDisposition::higher_priority_candidate
        : KBVectorDisposition::would_post_pending;
    return result;
}
} // namespace arcaderecomp_generated
