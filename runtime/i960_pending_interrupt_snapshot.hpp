// Intel 80960KB pending interrupt RECORD: offline/read-only analysis.
//
// Grounding: Intel 80960KB Programmer's Reference Manual (March 1988),
// Chapter 8 pp. 8-2 through 8-3 and 8-8 through 8-9. The first 36 bytes
// of the interrupt table contain a 32-bit priority mask (offset 0..3)
// and 32 vector bytes (offset 4..35). Same-priority pending vectors are
// serviced in decreasing vector order.
//
// This accepts an externally supplied fixed 36-byte snapshot. Neither the
// CPU nor the bus is read, modified or locked here. The actual CPU uses
// atomic, table-locking transactions; they are NOT implemented here.
// This cannot clear pending bits, change MODPC, or service an interrupt.
#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_generated {

enum class KBPendingSnapshotStatus : std::uint8_t {
    no_eligible_vector,
    eligible_candidate_only,
    inconsistent_priority_mask,
    reserved_vector_present
};

struct KBPendingSnapshotReview {
    KBPendingSnapshotStatus status = KBPendingSnapshotStatus::no_eligible_vector;
    std::uint32_t reported_priority_mask = 0u;
    std::uint32_t derived_priority_mask = 0u;
    unsigned vectors_set = 0u;
    unsigned eligible_count = 0u;
    unsigned highest_eligible_vector = 0u;
    unsigned highest_eligible_priority = 0u;
    // A candidate is NOT a vector chosen or serviced by the i960.
};

// The input may be made from synthetic RAM or unverified external bytes.
// It does NOT prove these 36 bytes were captured atomically from Intel
// hardware. Malformed vector/priority records are rejected, never silently
// interpreted as proof of an empty pending queue.
//
// current_priority MUST be explicitly provided from independently known
// CPU state. Priority 31 interrupts are always eligible for service even
// if current_priority is 31 (Intel KB special case).
inline KBPendingSnapshotReview review_kb_pending_snapshot(
    const std::array<std::uint8_t, 36>& record,
    unsigned current_priority) {
    if (current_priority > 31u)
        throw std::out_of_range("Intel KB program priority outside 0..31");

    KBPendingSnapshotReview result{};
    for (unsigned byte = 0u; byte < 4u; ++byte)
        result.reported_priority_mask |=
            static_cast<std::uint32_t>(record[byte]) << (8u * byte);

    for (unsigned vector = 0u; vector < 256u; ++vector) {
        const unsigned index = 4u + vector / 8u;
        const auto mask = static_cast<unsigned>(1u << (vector & 7u));
        if ((record[index] & mask) == 0u)
            continue;

        // The KB does not provide vectors 0..7, and reserves 244..251.
        // Even a set priority mask cannot legitimize those vectors.
        if (vector < 8u || (vector >= 244u && vector <= 251u)) {
            result.status = KBPendingSnapshotStatus::reserved_vector_present;
            return result;
        }
        const unsigned priority = vector / 8u;
        result.derived_priority_mask |= std::uint32_t{1u} << priority;
        ++result.vectors_set;
    }

    // Never expose even a candidate from a malformed/incoherent table.
    // Complete validation precedes ALL priority/eligibility selection.
    if (result.reported_priority_mask != result.derived_priority_mask) {
        result.status = KBPendingSnapshotStatus::inconsistent_priority_mask;
        return result;
    }
    for (unsigned vector = 8u; vector < 256u; ++vector) {
        const unsigned index = 4u + vector / 8u;
        if (!(record[index] & (1u << (vector & 7u))))
            continue;
        const unsigned priority = vector / 8u;
        if (priority != 31u && priority <= current_priority)
            continue;
        ++result.eligible_count;
        // Vectors increase monotonically with priority. The highest
        // vector number wins when equal priorities are pending.
        result.highest_eligible_vector = vector;
        result.highest_eligible_priority = priority;
    }
    if (result.eligible_count)
        result.status = KBPendingSnapshotStatus::eligible_candidate_only;
    return result;
}

} // namespace arcaderecomp_generated
