// Original ArcadeRecomp passive-configuration session composition.
// Owns existing input, empirical stream, recovery and startup components.
// This is a diagnostic integration layer, NOT the missing silicon acceptance
// decoder, Sega transport, mode/option discovery, or an implemented user circuit.
// See docs/FLEX8000_CONFIGURATION_SESSION.md. Qualified events come from the
// caller; a valid file or a byte count never invents CONF_DONE or a device error.
#pragma once
#include "flex8000_config_ingress.hpp"
#include "flex8000_config_recovery.hpp"
#include "epf8282_stream_decoder.hpp"
#include <optional>

namespace arcaderecomp_flex8000 {

enum class SessionPhase { idle, receiving, profile_ready, waiting_conf_done,
                          initializing, initialization_elapsed, profile_error,
                          device_error, startup_error, reset_asserted, reset_released };
struct ProfileFailure {
    StreamError error;
    std::size_t bit_position, bits_seen, records_checked;
};

class ConfigSession final {
public:
    // An owner/generation-bound software lifetime handle, not a hardware
    // acceptance certificate. Valid only during the lifetime of its owner.
    class Attempt {
        friend class ConfigSession;
        LoadingAttempt loading_;
        explicit Attempt(LoadingAttempt value) : loading_(value) {}
    public:
        Attempt(const Attempt&)=default;
        Attempt& operator=(const Attempt&)=default;
    };
    ConfigSession(LoadingMode mode, StreamEnvelope envelope)
        : mode_(mode), ingress_(mode), decoder_(envelope) {}
    ConfigSession(const ConfigSession&)=delete;
    ConfigSession& operator=(const ConfigSession&)=delete;
    ConfigSession(ConfigSession&&)=delete;
    ConfigSession& operator=(ConfigSession&&)=delete;

    // Caller establishes preparation, known high pins, inactive strobes and a
    // low loading clock. No POR/reset duration or default option is inferred.
    Attempt begin_observed_loading(AutoRestart option, PinLevel nconfig, PinLevel nstatus) {
        if (phase_!=SessionPhase::idle && phase_!=SessionPhase::reset_released)
            throw std::logic_error("session requires initial preparation or qualified reset");
        const auto handle=recovery_.begin_observed_loading({scheme(),option},nconfig,nstatus);
        ingress_.begin_loading(); decoder_.begin(); startup_.reset(); failure_.reset();
        phase_=SessionPhase::receiving;
        return Attempt(handle);
    }
    bool drive_dclk(Attempt attempt, bool high, std::uint8_t data) {
        require_receiving(attempt);
        return consume(ingress_.drive_dclk(high,data));
    }
    void drive_parallel(Attempt attempt, ParallelPins pins) {
        require_receiving(attempt); ingress_.drive_parallel(pins);
    }
    bool internal_falling_edge(Attempt attempt) {
        require_receiving(attempt); return consume(ingress_.internal_falling_edge());
    }

    // Explicit stream termination is a PROFILE check, not physical acceptance.
    // Even after the final bit, data stays unavailable until this succeeds.
    bool finish_profile(Attempt attempt) {
        require_receiving(attempt);
        // A parallel host can capture an extra byte without yet serializing a
        // bit. Refuse that buffered tail BEFORE completing the decoder.
        if (decoder_.bits_seen()==EPF8282StreamDecoder::kStreamBits && ingress_.pending_bits()!=0) {
            failure_=ProfileFailure{StreamError::extra_bits,decoder_.bits_seen(),
                                    decoder_.bits_seen(),decoder_.records_validated()};
            discard_data(); phase_=SessionPhase::profile_error; return false;
        }
        if (!decoder_.finish()) { discard_bad_profile(); return false; }
        ingress_.abort_loading(); phase_=SessionPhase::profile_ready;
        return true;
    }
    EPF8282StreamDecoder::PackedData decoded_data(Attempt attempt) const {
        require_current(attempt);
        if (phase_==SessionPhase::receiving)
            throw std::logic_error("profile is not complete");
        // Value copy only. Already returned copies cannot be revoked; a caller
        // must recheck its handle before using a retained copy as current data.
        return decoder_.packed_data();
    }

    // Independent physical/fixture observation supplied by the caller. Merely
    // finishing the file never calls this API. This strict diagnostic session
    // requires the complete measured profile before it can compare startup.
    // Earlier silicon release events are unsupported, NOT declared impossible.
    void observe_conf_done_release(Attempt attempt, StartupOptions options, PinLevel resolved) {
        require_current(attempt);
        if (phase_!=SessionPhase::profile_ready)
            throw std::logic_error("CONF_DONE observation needs this attempt's completed profile");
        // Construct/validate locally: bad options or unknown levels do not arm
        // startup or partially mutate the already completed profile.
        ConfigStartup next(options);
        next.begin_after_conf_done_release(); next.observe_conf_done(resolved);
        startup_.emplace(next); update_startup_phase();
    }
    void observe_conf_done(Attempt attempt, PinLevel resolved) {
        require_startup(attempt); startup_->observe_conf_done(resolved); update_startup_phase();
    }
    void qualified_startup_cycle(Attempt attempt, StartupClock source) {
        require_startup(attempt); startup_->qualified_cycle(source); update_startup_phase();
    }

    // Hardware-error input is independent of the empirical record checker.
    // Only the pre-startup loading window is modeled by this API.
    void observe_device_error(Attempt attempt, ConfigErrorCause cause) {
        require_current(attempt);
        if (phase_!=SessionPhase::receiving && phase_!=SessionPhase::profile_ready)
            throw std::logic_error("device-error observation outside supported loading window");
        recovery_.observe_device_error(cause);
        discard_data(); phase_=SessionPhase::device_error;
    }
    void assert_nconfig_low() {
        recovery_.assert_nconfig_low(); discard_data(); startup_.reset(); failure_.reset();
        phase_=SessionPhase::reset_asserted;
    }
    void release_nconfig_after_qualified_reset() {
        if (phase_!=SessionPhase::reset_asserted)
            throw std::logic_error("reset release requires an observed low assertion");
        recovery_.release_nconfig_after_qualified_reset(); phase_=SessionPhase::reset_released;
    }

    bool attempt_is_current(Attempt attempt) const noexcept {
        const bool usable=phase_==SessionPhase::receiving || phase_==SessionPhase::profile_ready ||
            phase_==SessionPhase::waiting_conf_done || phase_==SessionPhase::initializing ||
            phase_==SessionPhase::initialization_elapsed;
        return usable && recovery_.attempt_is_current(attempt.loading_);
    }
    SessionPhase phase() const noexcept { return phase_; }
    std::size_t bits_seen() const noexcept { return decoder_.bits_seen(); }
    unsigned pending_bits() const noexcept { return ingress_.pending_bits(); }
    std::optional<ProfileFailure> profile_failure() const noexcept { return failure_; }
    bool initialization_interval_elapsed() const noexcept {
        return phase_==SessionPhase::initialization_elapsed;
    }
    unsigned initialization_cycles() const noexcept {
        return startup_ ? startup_->initialization_cycles() : 0;
    }
    DrainDrive nstatus_drive() const noexcept {
        // A parser diagnostic cannot decide physical error/status pin behavior.
        if (phase_==SessionPhase::profile_error) return DrainDrive::unknown;
        return startup_ ? startup_->nstatus_drive() : recovery_.nstatus_drive();
    }
    DrainDrive conf_done_drive() const noexcept {
        if (phase_==SessionPhase::reset_asserted) return DrainDrive::sink_low;
        // No acceptance detector: before an explicit release observation this
        // composition does not claim to know the device's CONF_DONE drive.
        return startup_ ? startup_->conf_done_drive() : DrainDrive::unknown;
    }
    std::optional<bool> ready_nbusy(Attempt attempt) const {
        require_receiving(attempt); return ingress_.ready_nbusy();
    }
    BusDrive data_bus_drive(Attempt attempt) const {
        require_receiving(attempt); return ingress_.data_bus_drive();
    }
    // Intentionally no mutable subcomponent getters or user-mode success flag.
private:
    const LoadingMode mode_;
    ConfigIngress ingress_;
    EPF8282StreamDecoder decoder_;
    ConfigRecovery recovery_;
    std::optional<ConfigStartup> startup_;
    std::optional<ProfileFailure> failure_;
    SessionPhase phase_=SessionPhase::idle;
    ConfigScheme scheme() const noexcept {
        return mode_==LoadingMode::passive_serial ? ConfigScheme::passive_serial :
            mode_==LoadingMode::passive_parallel_sync ? ConfigScheme::passive_parallel_sync :
            ConfigScheme::passive_parallel_async;
    }
    void require_current(Attempt attempt) const {
        if (!attempt_is_current(attempt)) throw std::logic_error("stale or foreign configuration session attempt");
    }
    void require_receiving(Attempt attempt) const {
        require_current(attempt);
        if (phase_!=SessionPhase::receiving) throw std::logic_error("session is not receiving profile data");
    }
    void require_startup(Attempt attempt) const {
        require_current(attempt);
        if (!startup_) throw std::logic_error("no independently observed CONF_DONE release");
    }
    void discard_data() noexcept { ingress_.abort_loading(); decoder_.reset(); }
    void discard_bad_profile() noexcept {
        failure_=ProfileFailure{decoder_.error(),decoder_.failure_bit(),decoder_.bits_seen(),decoder_.records_validated()};
        discard_data(); phase_=SessionPhase::profile_error;
    }
    bool consume(std::optional<bool> bit) {
        if (bit && !decoder_.push_bit(*bit)) { discard_bad_profile(); return false; }
        return true;
    }
    void update_startup_phase() {
        switch (startup_->phase()) {
        case StartupPhase::waiting_conf_done: phase_=SessionPhase::waiting_conf_done; break;
        case StartupPhase::initializing: phase_=SessionPhase::initializing; break;
        case StartupPhase::initialization_elapsed: phase_=SessionPhase::initialization_elapsed; break;
        case StartupPhase::timeout_error: discard_data(); phase_=SessionPhase::startup_error; break;
        default: throw std::logic_error("unexpected composed startup state");
        }
    }
};
} // namespace arcaderecomp_flex8000
