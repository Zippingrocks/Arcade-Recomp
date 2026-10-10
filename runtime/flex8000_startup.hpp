// Original ArcadeRecomp functional post-configuration startup control.
// Source: Altera AN33 (June 2000 v3.03), printed pp. 58-63.
// Begins ONLY when an external, separately validated decoder/controller has
// actually released CONF_DONE. Counting uploaded bytes cannot arm this class.
// No stream acceptance, reset timing, electrical delays, register contents,
// individual clear/OE release cycles, or Sega serial replies are implemented.
#pragma once
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_flex8000 {

enum class PinLevel { unknown, low, high };
enum class DrainDrive { unknown, released, sink_low };
enum class PullUp { unknown, absent, present };
enum class StartupClock { unknown, dclk, internal_oscillator, clkusr };
enum class StartupTimeout { unknown, enabled, disabled };
enum class StartupPhase { unestablished, waiting_conf_done, initializing,
                          initialization_elapsed, timeout_error, reset_asserted };

// Open drain never actively drives high. A qualified external pull-up and
// release by EVERY contributor are required before a high level is known.
inline PinLevel resolve_open_drain(DrainDrive device, DrainDrive peers, PullUp pull) {
    const auto valid_drive=[](DrainDrive x) {
        return x==DrainDrive::unknown || x==DrainDrive::released || x==DrainDrive::sink_low;
    };
    if (!valid_drive(device) || !valid_drive(peers) ||
        (pull!=PullUp::unknown && pull!=PullUp::absent && pull!=PullUp::present))
        throw std::invalid_argument("invalid open-drain input");
    if (device==DrainDrive::sink_low || peers==DrainDrive::sink_low) return PinLevel::low;
    if (device==DrainDrive::unknown || peers==DrainDrive::unknown || pull!=PullUp::present)
        return PinLevel::unknown;
    return PinLevel::high;
}

struct StartupOptions {
    // Explicit integration parameters, not values decoded from HOTD1's stream.
    // Timeout and initialization clocks are deliberately separate: do not
    // infer the timeout clock from the CLKUSR initialization option.
    StartupClock timeout_clock = StartupClock::unknown;
    StartupClock initialization_clock = StartupClock::unknown;
    StartupTimeout timeout = StartupTimeout::unknown;
};

class ConfigStartup final {
public:
    static constexpr unsigned kTimeoutCycles=10, kInitializationCycles=10;
    explicit ConfigStartup(StartupOptions options) : options_(options) {
        require_clock(options.timeout_clock);
        require_clock(options.initialization_clock);
        if (options.timeout!=StartupTimeout::enabled && options.timeout!=StartupTimeout::disabled)
            throw std::invalid_argument("startup timeout option has not been established");
    }

    // Caller attests to the CONF_DONE RELEASE event, not merely end-of-file,
    // a record checksum match, 5120 bytes received, or a Sega TX command.
    // This method does not determine whether any configuration was accepted.
    void begin_after_conf_done_release() {
        if (phase_!=StartupPhase::unestablished)
            throw std::logic_error("startup already established; reset/reconfigure first");
        phase_=StartupPhase::waiting_conf_done;
        observed_done_=PinLevel::unknown;
        waited_=initialized_=0;
    }

    // Explicit settled-pin observation, independent of reading our output.
    // A high starts the initialization window; it is NOT immediate user mode.
    // Falling/unknown CONF_DONE during initialization is outside the modeled
    // behavior and refused before mutation, rather than invented as a pause.
    void observe_conf_done(PinLevel level) {
        if (level!=PinLevel::low && level!=PinLevel::high)
            throw std::invalid_argument("CONF_DONE needs a resolved digital level");
        if (phase_==StartupPhase::waiting_conf_done) {
            observed_done_=level;
            if (level==PinLevel::high) phase_=StartupPhase::initializing;
            return;
        }
        if (phase_==StartupPhase::initializing && level==PinLevel::high) return;
        throw std::logic_error("CONF_DONE transition outside supported startup window");
    }

    // One COMPLETE, externally qualified clock cycle, not a pin read or an
    // assumed edge. The caller establishes phase/setup/hold and event ordering.
    // No nanosecond duration or rising-versus-falling sampling phase is guessed.
    void qualified_cycle(StartupClock source) {
        require_clock(source);
        if (phase_==StartupPhase::unestablished || phase_==StartupPhase::reset_asserted)
            throw std::logic_error("no post-configuration startup window");
        if (phase_==StartupPhase::waiting_conf_done) {
            if (source!=options_.timeout_clock) return;
            if (observed_done_!=PinLevel::low)
                throw std::logic_error("unresolved CONF_DONE cannot count as low");
            if (waited_<kTimeoutCycles) ++waited_;
            if (waited_==kTimeoutCycles && options_.timeout==StartupTimeout::enabled)
                phase_=StartupPhase::timeout_error;
        } else if (phase_==StartupPhase::initializing && source==options_.initialization_clock) {
            if (++initialized_==kInitializationCycles)
                phase_=StartupPhase::initialization_elapsed;
        }
        // Completed and errored states do not restart through more clocks.
    }

    // Functional nCONFIG levels only. The caller must qualify the reset pulse
    // width/preparation interval. High alone never accepts another bitstream.
    void assert_nconfig_low() noexcept {
        phase_=StartupPhase::reset_asserted;
        observed_done_=PinLevel::unknown;
        waited_=initialized_=0;
    }
    void release_nconfig_high() {
        if (phase_!=StartupPhase::reset_asserted)
            throw std::logic_error("nCONFIG high without modeled low assertion");
        phase_=StartupPhase::unestablished;
    }

    StartupPhase phase() const noexcept { return phase_; }
    // Diagnostic count capped at ten, not total time when timeout is disabled.
    unsigned observed_wait_cycles_capped() const noexcept { return waited_; }
    unsigned initialization_cycles() const noexcept { return initialized_; }
    bool initialization_interval_elapsed() const noexcept {
        return phase_==StartupPhase::initialization_elapsed;
    }
    DrainDrive conf_done_drive() const noexcept {
        if (phase_==StartupPhase::reset_asserted) return DrainDrive::sink_low;
        if (phase_==StartupPhase::waiting_conf_done || phase_==StartupPhase::initializing ||
            phase_==StartupPhase::initialization_elapsed) return DrainDrive::released;
        // Do not guess what CONF_DONE does after a timeout or before acceptance.
        return DrainDrive::unknown;
    }
    DrainDrive nstatus_drive() const noexcept {
        if (phase_==StartupPhase::reset_asserted || phase_==StartupPhase::timeout_error)
            return DrainDrive::sink_low;
        if (phase_==StartupPhase::unestablished) return DrainDrive::unknown;
        return DrainDrive::released;
    }

private:
    const StartupOptions options_;
    StartupPhase phase_=StartupPhase::unestablished;
    PinLevel observed_done_=PinLevel::unknown;
    unsigned waited_=0, initialized_=0;
    static void require_clock(StartupClock source) {
        if (source!=StartupClock::dclk && source!=StartupClock::internal_oscillator &&
            source!=StartupClock::clkusr)
            throw std::invalid_argument("startup clock source has not been established");
    }
};
} // namespace arcaderecomp_flex8000
