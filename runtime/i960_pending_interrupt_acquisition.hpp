// Intel 80960KB pending table: read-only native bus-capture CONTRACT.
//
// Intel KB Programmer's Reference Manual (1988) 8-8..8-9 requires
// atomic locked read/modify/write. StrictBus does NOT implement it.
// A provider-declared snapshot is NOT independently authenticated.
#pragma once
#include "i960_interrupt_priority.hpp"
#include "i960_pending_interrupt_snapshot.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
namespace arcaderecomp_generated {

enum class KBPendingCaptureStatus : std::uint8_t {
    cpu_priority_unknown,
    invalid_interrupt_table_address,
    locked_provider_unavailable,
    locked_provider_refused,
    invalid_record,
    provider_asserted_unverified
};
struct KBPendingCaptureReview {
    KBPendingCaptureStatus status=KBPendingCaptureStatus::cpu_priority_unknown;
    std::uint32_t table_address=0u;
    unsigned program_priority=0u;
    KBPendingSnapshotReview snapshot{};
    // Metadata only. No original bytes, CPU mutation or hardware proof.
};
inline KBPendingCaptureReview review_kb_pending_from_native_bus(
    const CPU& cpu, const Bus& bus) {
    KBPendingCaptureReview result{};
    const auto known=kb_known_cpu_program_priority(cpu);
    if(!known)return result;
    result.program_priority=*known;
    const std::uint32_t address=cpu.interrupt_table_address;
    if(address==0u || (address&3u) || address>UINT32_MAX-35u) {
        result.status=KBPendingCaptureStatus::invalid_interrupt_table_address;
        return result;
    }
    result.table_address=address;
    if(!bus.read_pending_record_locked) {
        result.status=KBPendingCaptureStatus::locked_provider_unavailable;
        return result;
    }
    std::array<std::uint8_t,36> bytes{};
    if(!bus.read_pending_record_locked(bus.ctx,address,bytes.data(),bytes.size())) {
        // Partial provider scratch data must NEVER reach the caller.
        result.status=KBPendingCaptureStatus::locked_provider_refused;
        return result;
    }
    const auto reviewed=review_kb_pending_snapshot(bytes,*known);
    if(reviewed.status!=KBPendingSnapshotStatus::no_eligible_vector &&
       reviewed.status!=KBPendingSnapshotStatus::eligible_candidate_only) {
        result.status=KBPendingCaptureStatus::invalid_record;
        return result;
    }
    result.snapshot=reviewed;
    result.status=KBPendingCaptureStatus::provider_asserted_unverified;
    return result;
}
} // namespace arcaderecomp_generated
