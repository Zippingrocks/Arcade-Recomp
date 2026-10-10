# FLEX 8000 post-configuration startup window

Date: 2026-10-10. Base: `032086445c093bef022999de0e8ad14e54c703c9`.

**Sega Model 2C is NOT complete.** This change implements a bounded,
manufacturer-documented startup-control window. It does not establish that
HOTD1's upload was accepted, select Sega's loading mode or clock wiring, or
supply serial responses. The original game still stops at serial status.

## Specification and entry boundary

Altera's [AN33, Configuring FLEX 8000 Devices, June 2000 v3.03](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-),
printed pp. 58-63, distinguishes releasing the open-drain CONF_DONE output
from sensing the resulting net high. A pull-up cannot make that net high
while another open-drain participant holds it low. Initialization requires
ten clock cycles. When startup timeout is enabled, failure to see CONF_DONE
high within the ten-cycle window causes nSTATUS to be held low. With timeout
disabled, the device continues waiting for external release.

The related [Altera AN38, Configuring Multiple FLEX 8000 Devices](https://paperzz.com/doc/7534819/an038_02.pdf),
printed p. 73, describes a shared CONF_DONE net held low until all participants
release it. This is a manufacturer example, not a claim that Sega used a
multi-FPGA chain. Both references are manufacturer documents hosted by mirrors.

`runtime/flex8000_startup.hpp` starts only at an explicit, externally
established CONF_DONE-release event from a separate configuration controller.
It does NOT derive that event from 5,120 transmitted bytes, a Python checksum
match, an empty serializer, or a guessed Sega command. No complete stream
validator is supplied by this component.

## Implemented functional behavior

- Open-drain drive and resolved logic level are distinct types. Low dominates;
  high requires known releases and a pull-up; floating/unknown is not zero.
- CONF_DONE low waits. High starts, but does not complete, initialization.
- The enabled timeout triggers at cycle ten, not nine. Its error latches;
  more clocks cannot clear it. Disabling timeout permits indefinite waiting.
- Initialization needs ten separately qualified cycles after the high event.
  Pin reads and wrong-domain cycles do not advance either window.
- Functional nCONFIG-low assertion invalidates the current window and pulls
  both status outputs low. Release returns to an unestablished state, not to
  a silently re-accepted configuration. A new release event is necessary.
- Missing options, unknown pins, unsupported transitions and invalid clock
  sources are refused before changing state.

The enclosing board/controller MUST provide timeout policy and separately
identified timeout/initialization clock domains. AN33 identifies internal,
DCLK and optional CLKUSR initialization choices, but this pass does not locate
those option bits in HOTD1 or assume its timeout clock is the CLKUSR source.
Tests of every API clock pairing are software tests, not claims that every
pairing is wired on a real device.

## Deliberate exclusions

Cycles are complete, externally qualified events. Nanosecond delays, the
sampling edge/phase of the internal sequencer, setup/hold, reset pulse width,
POR duration and simultaneous transition ordering are not invented. A falling
CONF_DONE during initialization is refused as outside the modeled behavior.
CONF_DONE drive after a timeout is unknown rather than an invented low/high.
Automatic active-mode reconfiguration is not implemented.

`initialization_interval_elapsed()` reports this component's ten-cycle
condition. It does not reset physical or simulated LUT/register contents,
release user I/O at an invented intermediate cycle, or validate a user circuit.
AN33's clear-versus-output-enable ordering options need separate modeling.
No link was added to `model2c_bus.hpp`, `sega3155649_serial.hpp`, or the i960
emitter. FPGA configuration acceptance, gun-board transport/wiring, routing,
clocks, authentic replies and `0x00F80000` remain unresolved.

## Validation in this pass

The baseline CI source ZIP SHA-256 matched
`0d36ca266662a2d083fd2c4382c6ab16cb32f937c57f63e84ca7b7968d99cc7e`.
The untouched baseline passed **267 tests** locally.

Fourteen new tests compile native C++ under both installed GCC and Clang,
with `-Werror` and UndefinedBehaviorSanitizer. They check:

- all 27 device/peer/pull-up combinations against a separate Python oracle;
- 2,808 timeout/initialization traces per compiler against a Python count oracle;
- timeout 9/10 boundaries, disabled timeouts, wrong clock domains, read-side
  noninterference, unknown levels, reset/retry and independent participants;
- all 256 byte values through each existing PS/PPS/PPA input stage, proving
  that finishing serialization DOES NOT arm the new startup component.

Initial test-harness warning failures were corrected without suppressing
warnings. All 14 new tests then passed under both compilers. The full combined
suite passed **281 tests locally**. These are synthetic functional results,
not original-cabinet timing measurements.

A fresh actual-original-ROM audit again matched **29 chip fingerprints**.
The CPU SHA-256 remains
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
Fresh generated C++ retained 3,051 candidates / 3,042 emitting sites / nine
unsupported sites. Neither the CPU emitter nor that coverage changed here.

| Actual native regression | Successful steps | Deliberate boundary |
| --- | ---: | --- |
| Strict default | 1,904 | IP 0xA375C, disabled serial TX |
| Documented TX only | 1,910 | IP 0xA372C, missing status 0x01C0001A |

Both returned diagnostic exit 3. The TX-enabled run recorded channel 2 FF,
channel 1 01. No synthetic receive/status provider was enabled, and the new
startup component was not armed by either original-ROM run.

## Reproduce

```sh
python -m unittest discover -s tests -p test_flex8000_startup.py -v
python -m unittest discover -s tests -v
```

The tests contain no original game data. They run each installed GCC/Clang;
this pass had both. The metadata report is
`docs/reports/flex8000_startup_validation.json`. This subsystem window is not
completion of the [Model 2C gates](MODEL2C_DEFINITION_OF_DONE.md).
