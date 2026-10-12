// Evidence-bounded access contract for the SCSP DSP setting-prohibited span.
// This is not register storage and provides no read value or alias semantics.
#pragma once
#include <cstdint>

namespace arcaderecomp::scsp {

class DspProhibitedClearWindow final {
    std::uint64_t discarded_word_reads_ = 0;
    std::uint64_t zero_word_writes_ = 0;
public:
    static constexpr unsigned bytes = 0x40u;

    void invalidate() { *this = DspProhibitedClearWindow{}; }

    // The production HOTD sound program uses CLR.L only. Its mandatory reads
    // are discarded by the CPU, so accepting the transaction does not invent
    // undocumented readback data.
    bool read16_discard(unsigned offset) {
        if (offset >= bytes || (offset & 1u)) return false;
        ++discarded_word_reads_;
        return true;
    }

    // Only the observed zero word is accepted. Nonzero writes, byte accesses,
    // and value-bearing reads remain unsupported instead of guessing whether
    // the physical decode is an alias, an ignored write, or hidden storage.
    bool write16(unsigned offset, std::uint16_t value) {
        if (offset >= bytes || (offset & 1u) || value != 0u) return false;
        ++zero_word_writes_;
        return true;
    }

    std::uint64_t completed_discarded_word_reads() const {
        return discarded_word_reads_;
    }
    std::uint64_t completed_zero_word_writes() const { return zero_word_writes_; }
};

} // namespace arcaderecomp::scsp
