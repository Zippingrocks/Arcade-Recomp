// Synchronized synthetic 80960KB pending-table transaction MODEL.
//
// This is NOT a Model 2C/i960 hardware bus implementation and MUST NEVER
// be bound to strict original HOTD1 CPU execution. It uses an ordinary
// host std::mutex, not Intel's bus LOCK pin or its architected atomic
// pending-table read/modify/write sequence.
//
// It exists solely to test the pure draft transformations under concurrent
// agents and to define a fail-closed commit contract for future research.
#pragma once

#include "i960_pending_interrupt_record_edit.hpp"
#include <array>
#include <cstdint>
#include <mutex>

namespace arcaderecomp_generated {

enum class KBSyntheticTransactionStatus : std::uint8_t {
    applied,
    already_present,
    no_eligible_vector,
    invalid_vector,
    invalid_program_priority,
    invalid_original_record,
    commit_refused
};

struct KBSyntheticTransactionResult {
    KBSyntheticTransactionStatus status =
        KBSyntheticTransactionStatus::invalid_original_record;
    std::uint64_t committed_revision = 0u;
    // These are populated only after a successful atomic commit.
    // An idempotent post, empty take or failure cannot claim an IRQ.
    unsigned vector = 0u;
    unsigned priority = 0u;
};

class SyntheticKBPendingTable final {
public:
    using Record = std::array<std::uint8_t, 36>;
    struct DiagnosticSnapshot {
        Record record{};
        std::uint64_t revision = 0u;
    };

    // Initial bytes are UNTRUSTED TEST DATA; deliberately permitted to be
    // invalid so corruption rejection can be independently exercised.
    explicit SyntheticKBPendingTable(const Record& unverified_record = {})
        : record_(unverified_record) {}

    SyntheticKBPendingTable(const SyntheticKBPendingTable&) = delete;
    SyntheticKBPendingTable& operator=(const SyntheticKBPendingTable&) = delete;
    SyntheticKBPendingTable(SyntheticKBPendingTable&&) = delete;
    SyntheticKBPendingTable& operator=(SyntheticKBPendingTable&&) = delete;

    void set_commit_allowed_for_test(bool allowed) {
        const std::lock_guard<std::mutex> lock(mutex_);
        commit_allowed_ = allowed;
    }

    DiagnosticSnapshot diagnostic_snapshot_for_test() const {
        const std::lock_guard<std::mutex> lock(mutex_);
        return {record_, revision_};
    }

    KBSyntheticTransactionResult post_for_test(unsigned vector) {
        const std::lock_guard<std::mutex> lock(mutex_);
        // Read, validate, compute AND (if permitted) commit under ONE lock.
        return commit_locked(draft_kb_pending_post(record_, vector));
    }

    KBSyntheticTransactionResult take_for_test(unsigned hypothetical_priority) {
        const std::lock_guard<std::mutex> lock(mutex_);
        return commit_locked(
            draft_kb_pending_take(record_, hypothetical_priority));
    }

private:
    mutable std::mutex mutex_{};
    Record record_{};
    std::uint64_t revision_ = 0u;
    bool commit_allowed_ = true;

    KBSyntheticTransactionResult commit_locked(const KBPendingEdit& edit) {
        KBSyntheticTransactionResult result{};
        result.committed_revision = revision_;
        switch (edit.status) {
        case KBPendingEditStatus::applied:
            if (!commit_allowed_) {
                result.status=KBSyntheticTransactionStatus::commit_refused;
                return result;
            }
            // This assignment is indivisible to other users of THIS object,
            // not an emulation of Intel hardware memory/cache locking.
            record_=edit.resulting_record;
            ++revision_;
            result.committed_revision=revision_;
            result.vector=edit.candidate_vector;
            result.priority=edit.candidate_priority;
            result.status=KBSyntheticTransactionStatus::applied;
            return result;
        case KBPendingEditStatus::already_present:
            result.status=KBSyntheticTransactionStatus::already_present;
            return result;
        case KBPendingEditStatus::no_eligible_vector:
            result.status=KBSyntheticTransactionStatus::no_eligible_vector;
            return result;
        case KBPendingEditStatus::invalid_vector:
            result.status=KBSyntheticTransactionStatus::invalid_vector;
            return result;
        case KBPendingEditStatus::invalid_program_priority:
            result.status=KBSyntheticTransactionStatus::invalid_program_priority;
            return result;
        case KBPendingEditStatus::invalid_original_record:
            result.status=KBSyntheticTransactionStatus::invalid_original_record;
            return result;
        }
        return result; // Defensive fail-closed unknown status.
    }
};

} // namespace arcaderecomp_generated
