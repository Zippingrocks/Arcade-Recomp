// Original ArcadeRecomp functional configuration-error/restart boundary.
// Source: Altera AN33 v3.03 (June 2000), printed pp. 39, 58, 60, 62, 69.
// Schemes/options and hardware error events MUST be independently established.
// A software stream-profile mismatch is NOT a hardware CRC-error observation.
// No Sega transport, configuration acceptance, power/reset timing or user logic.
#pragma once
#include "flex8000_startup.hpp"
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace arcaderecomp_flex8000 {

enum class ConfigScheme { active_serial, active_parallel_up, active_parallel_down,
                          passive_serial, passive_parallel_sync, passive_parallel_async };
enum class AutoRestart { unknown, disabled, enabled };
enum class ConfigErrorCause { frame_error, external_nstatus_low };
enum class RecoveryPhase { unestablished, loading, error_latched,
                           restart_pulse, restart_released,
                           reset_asserted, reset_released };
struct RecoveryPolicy { ConfigScheme scheme; AutoRestart auto_restart; };
class ConfigRecovery;
struct LoadingAttempt { std::uint64_t generation; const ConfigRecovery* owner; };

inline bool is_active_scheme(ConfigScheme scheme) {
    switch (scheme) {
    case ConfigScheme::active_serial:
    case ConfigScheme::active_parallel_up:
    case ConfigScheme::active_parallel_down: return true;
    case ConfigScheme::passive_serial:
    case ConfigScheme::passive_parallel_sync:
    case ConfigScheme::passive_parallel_async: return false;
    }
    throw std::invalid_argument("unknown FLEX 8000 configuration scheme");
}

// AN33 table 9: actual settled nSP:MSEL1:MSEL0 levels, NOT file properties.
inline ConfigScheme decode_config_straps(PinLevel nsp, PinLevel msel1, PinLevel msel0) {
    const auto bit=[](PinLevel p)->unsigned {
        if(p!=PinLevel::low && p!=PinLevel::high)
            throw std::invalid_argument("mode strap level is not known");
        return p==PinLevel::high;
    };
    const unsigned v=4u*bit(nsp)+2u*bit(msel1)+bit(msel0);
    switch(v) {
    case 0: return ConfigScheme::active_serial;
    case 2: return ConfigScheme::passive_serial;
    case 4: return ConfigScheme::active_parallel_up;
    case 5: return ConfigScheme::passive_parallel_sync;
    case 6: return ConfigScheme::active_parallel_down;
    case 7: return ConfigScheme::passive_parallel_async;
    default: throw std::invalid_argument("reserved FLEX 8000 strap combination");
    }
}

class ConfigRecovery final {
public:
    static constexpr unsigned kRestartCycles=10;
    ConfigRecovery()=default;
    ConfigRecovery(const ConfigRecovery&)=delete;
    ConfigRecovery& operator=(const ConfigRecovery&)=delete;
    ConfigRecovery(ConfigRecovery&&)=delete;
    ConfigRecovery& operator=(ConfigRecovery&&)=delete;

    // The parent has prepared a real/explicitly simulated loading window and
    // qualified reset timings. Both observed nCONFIG and resolved nSTATUS are
    // high. This API does NOT assert that preparation elapsed or accept data.
    // Policy is supplied anew; no stale option bit is assumed after reset.
    LoadingAttempt begin_observed_loading(RecoveryPolicy policy,
                                         PinLevel nconfig, PinLevel nstatus) {
        validate_policy(policy);
        if(nconfig!=PinLevel::high || nstatus!=PinLevel::high)
            throw std::invalid_argument("loading requires known high nCONFIG and nSTATUS");
        if(phase_!=RecoveryPhase::unestablished && phase_!=RecoveryPhase::restart_released &&
           phase_!=RecoveryPhase::reset_released)
            throw std::logic_error("loading needs initial preparation or a qualified restart");
        next_generation();
        policy_=policy; phase_=RecoveryPhase::loading; cycles_=0;
        return {generation_,this};
    }

    // Caller supplies an independently established device error, NOT merely
    // EPF8282StreamDecoder::failed. Incrementing generation invalidates access
    // under the old attempt. Parent MUST discard staged data and upstream bits.
    void observe_device_error(ConfigErrorCause cause) {
        if(cause!=ConfigErrorCause::frame_error && cause!=ConfigErrorCause::external_nstatus_low)
            throw std::invalid_argument("unsupported configuration error source");
        if(phase_!=RecoveryPhase::loading)
            throw std::logic_error("no active loading attempt for error observation");
        next_generation(); cycles_=0;
        phase_=policy_.auto_restart==AutoRestart::enabled
            ? RecoveryPhase::restart_pulse : RecoveryPhase::error_latched;
    }

    // Qualified COMPLETE cycles. Only the INTERNAL oscillator advances the
    // documented active-mode restart pulse, never DCLK/CLKUSR or a pin read.
    // No oscillator frequency, propagation delay or sampling phase is guessed.
    void qualified_cycle(StartupClock source) {
        if(source!=StartupClock::internal_oscillator && source!=StartupClock::dclk &&
           source!=StartupClock::clkusr)
            throw std::invalid_argument("unknown recovery clock source");
        if(phase_==RecoveryPhase::restart_pulse && source==StartupClock::internal_oscillator) {
            if(++cycles_==kRestartCycles) phase_=RecoveryPhase::restart_released;
        }
        // Further clocks do not establish a new stream or clear a latched error.
    }

    // Functional low/high events, NOT a reset-pulse-width or POR simulation.
    // The first low invalidates the old attempt. Repeated low observations do
    // not create more generations. Release alone cannot create a loading window.
    void assert_nconfig_low() {
        if(phase_==RecoveryPhase::reset_asserted) return;
        next_generation(); cycles_=0;
        phase_=RecoveryPhase::reset_asserted;
    }
    void release_nconfig_after_qualified_reset() {
        if(phase_!=RecoveryPhase::reset_asserted)
            throw std::logic_error("nCONFIG release requires a prior low assertion");
        phase_=RecoveryPhase::reset_released;
    }

    bool attempt_is_current(LoadingAttempt attempt) const noexcept {
        return attempt.owner==this && phase_==RecoveryPhase::loading &&
               generation_==attempt.generation;
    }
    void require_attempt(LoadingAttempt attempt) const {
        if(!attempt_is_current(attempt)) throw std::logic_error("stale or unavailable loading attempt");
    }
    RecoveryPhase phase() const noexcept { return phase_; }
    unsigned restart_cycles() const noexcept { return cycles_; }
    std::uint64_t generation() const noexcept { return generation_; }
    DrainDrive nstatus_drive() const noexcept {
        if(phase_==RecoveryPhase::error_latched || phase_==RecoveryPhase::restart_pulse ||
           phase_==RecoveryPhase::reset_asserted) return DrainDrive::sink_low;
        if(phase_==RecoveryPhase::loading || phase_==RecoveryPhase::restart_released)
            return DrainDrive::released;
        return DrainDrive::unknown;
    }
    // Intentionally no CONF_DONE, accepted-image or initialized-user-circuit API.
private:
    RecoveryPhase phase_=RecoveryPhase::unestablished;
    RecoveryPolicy policy_{ConfigScheme::passive_serial,AutoRestart::unknown};
    std::uint64_t generation_=0;
    unsigned cycles_=0;
    static void validate_policy(RecoveryPolicy p) {
        const bool active=is_active_scheme(p.scheme);
        if(p.auto_restart!=AutoRestart::enabled && p.auto_restart!=AutoRestart::disabled)
            throw std::invalid_argument("auto-restart option has not been established");
        if(p.auto_restart==AutoRestart::enabled && !active)
            throw std::invalid_argument("AN33 auto-restart option is active-mode only");
    }
    void next_generation() {
        if(generation_==std::numeric_limits<std::uint64_t>::max())
            throw std::overflow_error("loading generation exhausted");
        ++generation_;
    }
};
} // namespace arcaderecomp_flex8000
