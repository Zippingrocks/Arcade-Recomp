# FLEX 8000 configuration errors: mode-specific recovery and stale-load rejection

Date: 2026-10-10. Base commit: `37bff28efbf6ee48931a16a095dbe3bdf7cefa03`.

**Model 2C is NOT complete. No Sega transport or acceptance response was added.**
This pass implements generic, manufacturer-documented configuration-error
handling after an explicitly established loading window. It does not detect
physical CRC errors, identify Sega mode straps, decode header option bits,
or choose a status response for the original game.

## Specification and the mode restriction

Primary technical author: Altera, *Application Note 33: Configuring FLEX 8000
Devices*, June 2000 v3.03. The manufacturer's text is available on a
[document mirror](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-).
Printed page 39 describes an error-restart pulse of ten internal clock cycles;
Table 8 on page 58 limits the Auto-Restart Configuration on Frame Error option
to AS/APU/APD. Table 9 on page 60 maps nSP:MSEL1:MSEL0 to six schemes and two
reserved combinations. Page 62 describes external nSTATUS-low errors and
nCONFIG reset/restart. Page 69 describes detected frame errors halting loading.

Accordingly, passive PS/PPS/PPA operation is not assigned an automatic restart
just because a hypothetical policy requests one. Unsupported policy/strap
combinations are diagnostic errors, not invented silicon behavior. The pin
scheme is supplied from settled, known observations; a TTF or SOF file alone
cannot select it. Internal-clock cycles, not status reads, advance a supported
active-mode restart pulse. Released open-drain status does not imply the net
is high while another participant holds it low.

## Original implementation

`runtime/flex8000_config_recovery.hpp` introduces a bounded `ConfigRecovery`
state machine and the published strap decoder. The new class reuses the
existing open-drain and clock-domain types; it does not replace previous
input, startup or stream-decoder implementations.

A parent explicitly establishes loading with a known scheme/policy and
observed high nCONFIG/nSTATUS. A separate device-error observation invalidates
the loading attempt and sinks nSTATUS. With manual recovery, more clocks and
reads cannot clear that state. The parent must assert nCONFIG low, qualify
its reset, release it, and establish a fresh prepared loading window.

With a supported active-mode policy, ten complete, qualified INTERNAL clock
cycles release the restart pulse. External DCLK and CLKUSR cycles do not
count. Release only permits a fresh loading-boundary observation; it does
not itself begin a stream, accept configuration, or arm initialization.
A low/floating/unknown resolved status still blocks the new attempt.

Loading-attempt handles bind both generation and owning instance. Errors and
reset invalidate old handles; cross-instance handles are rejected, even when
the two controllers have equal generation numbers. These are software lifetime
guards, NOT cryptographic credentials or proof of physical acceptance. The
controller is noncopyable/nonmovable so its owner identity stays stable.

The parent integration example in the native probe discards the decoder and
aborts any partially serialized byte when a simulated device error arrives.
It then reloads from the beginning after an explicitly simulated reset and
preparation event. A caller must not reuse the old handle or stale serializer.

### Deliberate boundaries

An `EPF8282StreamDecoder` profile mismatch does **not** automatically invoke
the hardware-error API. The empirical framing/polynomial model is not a
complete silicon error detector. Conversely, a separately supplied hardware
error can invalidate a load even if its data matches that profile.

The API consumes qualified digital events, not raw electrical waveforms.
No POR interval, reset pulse width, oscillator frequency/phase, setup/hold,
propagation delay or physical error-sampling latency has been synthesized.
Reset release leaves status unknown until another preparation observation;
it is not an assumption of instantaneous hardware readiness. Repeated error
notifications during recovery are rejected rather than assigned an unproven
retrigger policy. Brownout, user-mode operation and active EPROM address/data
sequencing remain outside this class.

There is intentionally no CONF_DONE or accepted-user-circuit output. No code
in the i960 emitter, Sega bus, serial-response model or existing configuration
components changed. The original `0x00F80000` device remains unidentified.

## Validation performed

The baseline source artifact matched SHA-256
`1a91765fbd1b20a85365f732b986b1385f3e42bb4ad7bd27a3a054ed138899df`;
the complete untouched baseline passed 296 tests locally.

Fifteen new test methods cover all eight strap combinations, reserved/unknown
inputs, active/passive policy restrictions, exact cycle boundaries, clock
source separation, reset during every partial restart position, external holds,
read-side noninterference, owner/generation lifetime, independent controllers,
explicit parent discard and metadata/file protections. The native state tests
run under both GCC and Clang, with warnings as errors and UndefinedBehaviorSanitizer.
An independent Python oracle checks **1,242 state traces per compiler**.

The combined full local suite passed **311 tests**. The original-data probe
was also compiled separately with each compiler and produced identical metadata.

### Original upload under explicitly synthetic failure events

The original uploaded `hotdo.7z` matched all 29 chip size/CRC32/SHA-1 entries.
Its reconstructed 2-MiB maincpu SHA-256 remains
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

The probe tests 220 interruption points in each of PS/PPS/PPA: every one of
212 record tails plus eight prefix/sub-byte/end positions. For all **660
trials per compiler**, the old handle was invalidated, staged data and pending
serializer bits were discarded, passive mode stayed error-latched without
a reset, and a fresh qualified attempt reproduced all **37,524 data bits**
from the unchanged original 5,120-byte upload. Expected packed data is computed
with the pre-existing independent Python mapping, not from the new controller.

These are **original DATA with invented pin/error/preparation events**, not
captured Sega errors, actual hardware reset timing, or original-game execution
through the error paths. Successful reload never armed `ConfigStartup`.
The normal runtime was not connected to this probe.

`arcaderecomp.config_recovery_probe` verifies original file hashes before
compilation, uses temporary private inputs, and exports only metadata. It
rejects incomplete counts, duplicate fields, false success claims and attempts
to overwrite the original image, including through a hard link. The synthetic
native test separately demonstrates that wrong expected data cannot produce
a success report. Configuration bytes and game-derived binaries are not published.

### Fresh original-game regression

A new original-ROM AOT build retained 3,051 candidate sites, 3,042 emitting
sites and nine unsupported sites. These are unchanged static candidates,
not a completed-game percentage. The new strict native executable returned:

| Configuration | Successful instructions | Deliberate boundary |
| --- | ---: | --- |
| Strict default | 1,904 | Disabled serial TX, IP `0xA375C` |
| Documented TX only | 1,910 | Missing status `0x01C0001A`, IP `0xA372C` |

Both returned diagnostic exit 3; the second logged TX2=FF and TX1=01. Neither
used synthetic RX/status data or the new recovery component.

## Reproduction and remaining gates

```sh
python -m unittest discover -s tests -p test_flex8000_config_recovery.py -v
python -m unittest discover -s tests -p test_config_recovery_probe.py -v
python -m unittest discover -s tests -v
# Private verified original maincpu only; no network/ROM fetching:
python -m arcaderecomp.config_recovery_probe \
  --image build/hotd1/maincpu.bin \
  --output build/research/hotdo-config-recovery.json
```

The private-data check defaults to GCC and Clang; repeated `--cxx` selects
explicit alternatives. Metadata lives in `docs/reports/hotdo_config_recovery.json`.

Still missing: original board mode/option wiring and transport, complete
header/length/acceptance and error detection, routing/clock/register behavior,
authentic gun replies, and the separate mainboard register. This component
fills a documented recovery branch; it does not bridge the real serial-status
blocker or satisfy the [Model 2C completion gates](MODEL2C_DEFINITION_OF_DONE.md).
