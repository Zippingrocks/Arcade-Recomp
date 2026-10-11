// Intel 80960KB pending interrupt table: PURE record mutation DRAFTS.
// Intel 80960KB Programmer's Reference Manual (Mar 1988), Ch. 8 pp. 8-2,
// 8-3, 8-8 and 8-9. No CPU state changes, bus lock, atomic RAM commit,
// IRQ entry/return, or actual Model 2C hardware transaction occurs here.
// Returned records MUST NEVER be written by piecemeal normal bus callbacks.
#pragma once
#include "i960_pending_interrupt_snapshot.hpp"
#include <array>
#include <cstdint>
namespace arcaderecomp_generated {

enum class KBPendingEditStatus : std::uint8_t {
    applied, already_present, no_eligible_vector, invalid_vector,
    invalid_program_priority, invalid_original_record
};
struct KBPendingEdit {
    KBPendingEditStatus status = KBPendingEditStatus::invalid_original_record;
    std::array<std::uint8_t,36> resulting_record{};
    unsigned candidate_vector = 0u;
    unsigned candidate_priority = 0u;
    // Error results are zeroed; a successful result is still UNCOMMITTED.
};
inline bool kb_pending_vector_valid(unsigned v) {
    return v >= 8u && v <= 255u && (v < 244u || v > 251u);
}
inline bool kb_pending_record_valid(const std::array<std::uint8_t,36>& bytes) {
    const auto scan=review_kb_pending_snapshot(bytes,0u);
    return scan.status==KBPendingSnapshotStatus::no_eligible_vector ||
           scan.status==KBPendingSnapshotStatus::eligible_candidate_only;
}
inline KBPendingEdit draft_kb_pending_post(
    const std::array<std::uint8_t,36>& before, unsigned vector) {
    KBPendingEdit result{};
    if(!kb_pending_vector_valid(vector)) {
        result.status=KBPendingEditStatus::invalid_vector;
        return result;
    }
    if(!kb_pending_record_valid(before))return result;
    const unsigned level=vector/8u;
    const unsigned idx=4u+level;
    const auto flag=static_cast<std::uint8_t>(1u<<(vector&7u));
    result.resulting_record=before;
    result.candidate_vector=vector;
    result.candidate_priority=level;
    if(before[idx]&flag) {
        result.status=KBPendingEditStatus::already_present;
        return result;
    }
    result.resulting_record[idx] |= flag;
    result.resulting_record[level/8u] |=
        static_cast<std::uint8_t>(1u<<(level&7u));
    result.status=KBPendingEditStatus::applied;
    return result;
}
inline KBPendingEdit draft_kb_pending_take(
    const std::array<std::uint8_t,36>& before, unsigned current_priority) {
    KBPendingEdit result{};
    if(current_priority>31u) {
        result.status=KBPendingEditStatus::invalid_program_priority;
        return result;
    }
    const auto scan=review_kb_pending_snapshot(before,current_priority);
    if(scan.status!=KBPendingSnapshotStatus::no_eligible_vector &&
       scan.status!=KBPendingSnapshotStatus::eligible_candidate_only)
        return result;
    if(scan.status==KBPendingSnapshotStatus::no_eligible_vector) {
        result.status=KBPendingEditStatus::no_eligible_vector;
        result.resulting_record=before; // Valid source; no mutation.
        return result;
    }
    const unsigned vector=scan.highest_eligible_vector;
    const unsigned level=vector/8u;
    const unsigned idx=4u+level;
    result.resulting_record=before;
    result.candidate_vector=vector;
    result.candidate_priority=level;
    result.resulting_record[idx] &=
        static_cast<std::uint8_t>(~(1u<<(vector&7u)));
    // Only the FINAL vector of a priority permits its priority-bit clear.
    if(result.resulting_record[idx]==0u)
        result.resulting_record[level/8u] &=
            static_cast<std::uint8_t>(~(1u<<(level&7u)));
    result.status=KBPendingEditStatus::applied;
    return result;
}
} // namespace arcaderecomp_generated
