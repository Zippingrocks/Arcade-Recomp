# One owned passive-configuration session

Date: 2026-10-10. Base: `7fde47a2a7a9b68aad5904b044e415a0c7df1461`.

**Model 2C is NOT complete. This is integration of existing configuration
components, not new proof of FPGA acceptance or a Sega transport implementation.**

## What was missing between the previous components

The input stage, empirical stream decoder, error recovery and startup interval
were individually available. Earlier probes had to manually abort the serializer,
reset the decoder and check the recovery generation in the correct order. There
was no shared owner enforcing those requirements across the complete session.

`runtime/flex8000_config_session.hpp` now owns all four. They remain independently
usable, but a session exposes no mutable references to its subcomponents. Its
owner/generation-bound handle is checked on data, pin, error and startup operations.
A reset or explicit loading error invalidates the handle and discards both decoded
staging and pending input bits. A startup timeout likewise makes the former image
unavailable through the session. A subsequent load requires qualified reset and a
fresh preparation observation; it cannot resume an old partially shifted byte.

Returned data snapshots are ordinary value copies. They cannot be retroactively
erased from a caller's memory. Callers must recheck their session handle before
using retained data as the current configuration. Handles are lifetime guards,
not cryptographic or hardware acceptance credentials, and are valid only during
the lifetime of their owner. Session objects cannot be copied or moved.

## File completion, physical completion and initialization remain separate

The supported flow is:

1. Explicitly establish a prepared PS, PPS or PPA loading window, known high
   nCONFIG/nSTATUS, the disabled passive-mode restart policy, inactive strobes
   and low loading clock.
2. Deliver qualified input events through the existing native input stage into
   the existing incremental record decoder. Even the final bit does not expose
   data until an explicit profile finish operation succeeds.
3. Make checked configuration data available, but **do not generate CONF_DONE**.
4. Only a separately established caller-supplied CONF_DONE release observation
   can start the existing post-configuration controller. A known resolved low
   waits; a known high begins its separately counted initialization interval.
5. Count explicitly supplied qualified startup-clock cycles. No reading API
   advances clocks. An elapsed interval is not proof that the user circuit has
   been decoded, initialized internally, or executed.

This is a strict diagnostic integration contract, not a claim that physical
silicon always releases CONF_DONE exactly at the end of the opaque file profile.
Earlier physical release events cannot yet be evaluated by this session. Startup
options and clock sources are explicit parameters, not recovered header bits or
inferred Sega wiring. The generic startup component's accepted parameter space
is not independently certified here as every legal silicon option combination.

Altera's primary technical description is *Application Note 33: Configuring FLEX
8000 Devices*, June 2000 v3.03, available on this
[manufacturer-document mirror](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-).
Printed pp. 56-63 describe reconfiguration, option restrictions, reset and
CONF_DONE/startup behavior; p. 69 describes configuration errors. The session
composes the previously implemented behavior rather than importing emulator code.
Physical reset preparation, electrical timing and silicon acceptance remain open.

## A captured byte can outlive the last delivered bit

In a parallel mode, the input stage can capture an additional byte while the
stream decoder has received exactly 40,960 bits: none of the extra byte's bits
need have been clocked yet. Finishing only the decoder would miss that pending
input. The session explicitly checks the serializer too, rejects the buffered
extra tail before finishing, and discards both buffers. Its `extra_bits` diagnostic
at position 40,960 denotes this extra captured input; it does not claim that those
bits reached a physical FPGA or that silicon asserted an error pin.

Truncation and empirical profile mismatches also stop the software session and
retain only diagnostic position/count metadata. They do **not** call the separate
hardware-error API. Physical nSTATUS drive is reported unknown after a software
profile failure, not falsely high, low or ready. A separately supplied hardware
error can still invalidate an otherwise matching configuration before startup.

## Validation actually run

The downloaded baseline source ZIP matched its CI digest:
`31b9619e12607d468c9c341a455364fbd5511d0ff11de951d62c09dd8d329cfe`.
The untouched baseline passed **311 tests** locally.

Fourteen new native-session tests compile with GCC and Clang, warnings treated as
errors and UndefinedBehaviorSanitizer enabled. They check preparation/policy,
foreign and stale handles, partial-byte resets, device errors versus parser
failures, truncation, extra captured data, exception-safe startup arguments,
external holds, separate clocks, timeout invalidation and reset at every modeled
startup phase. A two-bit empirical-check collision still produces different data
without manufacturing configuration success.

Four additional tests validate metadata, baseline-hash enforcement, output/input
alias protection and the complete probe on invented data. Deliberately supplying
wrong expected decoded data fails without printing a success report.

The complete updated local suite passed **329 tests**.

### Original payload, synthetic events

`arcaderecomp.config_session_probe` compiles the integration probe under GCC and
Clang and checks its entire report. All input data is private and temporary;
only counts, hashes and evidence classifications are exported.

For each compiler, the original payload passed:

| Experiment | Measured result |
| --- | ---: |
| Loading modes | 3 (PS, PPS, PPA) |
| Interruption positions per mode | 221 |
| Explicit reset trials | 663 |
| Explicit device-error trials | 663 |
| Reloads matching the independent Python decoder | 1,326 |
| Old handles rejected after reloading | 1,326 |
| Startup timeouts invalidating decoded-data access | 3 |
| Separately injected completion/startup sequences | 3 |

The interruption set includes all 212 record tails, zero bits, sub-byte and
preamble boundaries, and the final stream positions. Reloaded outputs match all
37,524 decoded data bits. GCC and Clang produced identical metadata reports.

**All pin, error, preparation and completion observations in this probe are
synthetic.** The payload is original; these are not original-cabinet captures,
physical FPGA acceptance, configured-circuit execution or continuous game boot.
The production Sega serial model is not connected to the session.

### Fresh original-game regression

All **29 original hotdo chips** matched size, CRC32 and SHA-1 again. The rebuilt
maincpu SHA-256 is
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
The fresh native build retains the baseline static graph: 3,051 candidates,
3,042 native-emitting sites and nine unsupported sites. This pass does not
increase those figures or claim a game-completion percentage.

| Run | Successful native instructions | Deliberate stop |
| --- | ---: | --- |
| Default strict | 1,904 | Disabled TX at IP `0xA375C` |
| Documented TX only | 1,910 | Missing serial status `0x01C0001A`, IP `0xA372C` |

Both returned diagnostic exit 3. The second recorded TX2=FF and TX1=01. No
artificial receive/status provider or new configuration session was connected.

## Reproduce

```sh
python -m unittest discover -s tests -p test_flex8000_config_session.py -v
python -m unittest discover -s tests -p test_config_session_probe.py -v
python -m unittest discover -s tests -v
# Requires a previously built private original maincpu image; does not fetch ROMs.
python -m arcaderecomp.config_session_probe \
  --image build/hotd1/maincpu.bin \
  --output build/hotd1/config-session-report.json
```

## Still open

This joins tested software stages without selecting Sega's physical loading mode,
transport or pin wiring. Header option meanings, the silicon acceptance decision,
FPGA routing/register/clock behavior, authentic gun-board replies, and the
separate `0x00F80000` register still need evidence and implementation. Active EPROM
loading, brownout and user-mode operation are not implemented by this session.
No Model 2C completion gate or authentic boot advance is being declared.
