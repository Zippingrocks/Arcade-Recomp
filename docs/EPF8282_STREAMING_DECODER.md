# EPF8282 incremental configuration-data path

Date: 2026-10-10. Base: `73e42021b82cc14a2fa51e086fe21d031345799f`.

**Model 2C is NOT complete.** This pass connects native input-stage output to
an independently authored streaming implementation of the previously measured
serial-record/SOF-data mapping. A matching data profile is deliberately NOT
silicon acceptance, configuration completion or proof of Sega's wiring.

## What changes from the earlier passes

The existing C++ PS/PPS/PPA input stages emit serial bits. The previous
record decoding was an offline Python operation. The new
`runtime/epf8282_stream_decoder.hpp` consumes those bits incrementally,
checks complete records, stages their data and reconstructs the packed
configuration-data representation entirely in native C++.

The experimental pipeline runs all three input modes through the same
new decoder, then compares its result with `flex8000_sram.py`'s independent
Python mapping. It does not connect either component to Sega MMIO or call
`ConfigStartup.begin_after_conf_done_release()`.

## Specification: published behavior versus measured representation

[Altera AN33, June 2000 v3.03](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-),
printed p. 69, documents checking configuration frames as they are loaded and
halting configuration with nSTATUS low on a detected CRC mismatch. Printed
pp. 64-65 describe headers, framing and the shared TTF representation.

That manufacturer text **does not give the polynomial, exact field positions
or the complete acceptance sequence implemented here**. Those particulars
come from the project's earlier measured EPF8282 profile, checked against
archived non-Sega compiler output and the original HOTD1 upload. The empirical
model remains: 31 opaque prefix bytes, 212 records of 192 bits, and one opaque
suffix byte. Each record contains one fixed zero, 177 data bits, eight check
bits and six fixed ones. The 185 data/check bits have residue 0xFF modulo
polynomial 0x111. See the [existing mapping implementation](../arcaderecomp/flex8000_sram.py)
and its tests; this pass does not refit that model.

The native checker evaluates ascending polynomial coefficients in constant
8-bit state rather than reproducing Python's arbitrary-width long division.
Its data mapping reverses the complete 37,524-bit data vector, not individual
bytes or records. Unused high bits in the 4,691-byte packed representation
remain zero.

## Input, failure and publication boundaries

An explicit envelope object supplies the expected prefix and suffix. They
are opaque comparisons, not decoded device options. The original-ROM probe
gets them from the separately hash-verified input. This is not independent
validation of the envelope's hardware meaning.

`begin()` opens a diagnostic stream. Each qualified incoming bit advances it
once. Pauses and inspections cannot advance it. No full image is accessible
until all bits pass the profile checks AND the caller explicitly invokes
`finish()`. This end-of-input declaration is not an FPGA end-of-configuration
signal.

A framing/check/envelope mismatch, truncated finish or extra bit before finish
latches a diagnostic error. Staged data is discarded and unavailable. Further
feeding cannot recover implicitly; `reset()` followed by `begin()` is needed.
Callers integrating an aborted stream must also abort/reset their upstream
input stage, not feed its leftover serialized bits into the next capture.
A returned packed-data snapshot is a value copy: resetting the decoder does
not retroactively invalidate a copy already held by the caller.

These choices are conservative software integrity/lifetime rules. They do
not claim the FPGA's precise partial-write, recovery, synchronization or
error-pin timing behavior. There is no nSTATUS/CONF_DONE output or success
callback on the decoder. In particular, no guessed nSTATUS error pulse is
inferred from a software profile mismatch.

## A check is not authentication

The native test flips two data bits twelve positions apart. Their difference
is x^12+1, divisible by the measured polynomial x^8+x^4+1. The altered frame
therefore still passes the empirical record check, although its decoded data
changes. This confirms the limitation already present in the Python model;
it is not a new claim that physical silicon necessarily accepts that stream.

The original-image and upload SHA-256 checks stay separate. Comparing the
entire decoded result with the independent expected data detects a changed
image even when the record relation alone does not. Neither check supplies
physical pin observations, routing, register initialization or a user circuit.

## Measured validation

The downloaded baseline source matched CI SHA-256
`00eb9558a9057743e3ab51f4e03c6cb93b821c2ffb42c706bc3debc8ec7d546e`.
The untouched baseline passed **281 tests** locally. The combined suite
passes **296 tests** locally after adding fifteen tests.

Native semantic tests run under both installed GCC and Clang, with warnings
as errors and UndefinedBehaviorSanitizer. A separately implemented Python
bit-by-bit oracle supplies expected packed data. The checks include:

- Every bit position in the first, middle and last records: 576 single-bit
  record mutations per compiler, all rejected with the expected diagnostic
  location and no exposed partial image.
- All 256 prefix/suffix bit mutations per compiler, all rejected against
  the original expected envelope.
- Truncation at each record tail and selected sub-byte boundaries, extra
  data, arbitrary feed pauses, explicit finish and reset at all 192 offsets
  within a record.
- Correct global bit ordering, absence of staged-image access, independent
  snapshot lifetime and the deliberate two-bit collision.
- All three existing input paths on artificial data, unchanged startup
  state, incorrect expected-data rejection, exact metadata schemas, ROM-hash
  checks and output-over-input protection (including hard links).

### Actual original upload through the native pipeline

The original `hotdo.7z` again matches all 29 expected chip fingerprints.
The reconstructed CPU SHA-256 is
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`;
upload SHA-256 remains
`de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.

The new probe ran with both GCC and Clang. In EACH of PS, PPS and PPA it
processed **40,960 input bits**, validated **212 complete records**, and
reconstructed **37,524 data bits** exactly matching the independent Python
result. The packed-data SHA-256 is
`5144cf9b156a27a41e53e17a31aa6efb098fcce448fbf9eed1de9a1bc6733f09`.
The compilers produced identical metadata. Actual pin/clock stimulus in all
three paths was synthetic. Successful profile parsing left the separately
instantiated startup controller unestablished and its output claims unknown.

The native probe compares private bytes in-process and emits metadata only.
Its Python wrapper verifies the original hashes BEFORE invoking native
code; temporary input/expected files are removed on exit. Neither original
payload bytes nor generated game code are committed.

### Actual original-game regression

A freshly generated and compiled strict native probe still stops at:

| Mode | Successful instructions | Boundary |
| --- | ---: | --- |
| Strict default | 1,904 | IP 0xA375C, disabled serial TX |
| Documented TX only | 1,910 | IP 0xA372C, unavailable status 0x01C0001A |

Both returned diagnostic exit 3. The second recorded TX2=FF and TX1=01.
No synthetic receive/status provider was enabled. The code graph remains
3,051 candidates / 3,042 native-emitting sites / nine unsupported sites.
No CPU-emitter, Sega bus, serial-response or existing startup code changed.

## Remaining acceptance gap

A fully matched empirical stream gives usable decoded DATA for continued
research, not proof of the configured circuit. Still unresolved: complete
header/options interpretation, hardware CRC/acceptance and recovery behavior,
Sega board loading mode and intervening transport, routing configuration,
clock/reset/register behavior, authentic replies, and the separate
0x00F80000 board address. Issues #4/#6 remain open.

## Reproduction

```sh
python -m unittest discover -s tests -p test_epf8282_stream_decoder.py -v
python -m unittest discover -s tests -v
# Requires an already verified local original CPU image; no network request:
python -m arcaderecomp.stream_decode_probe \
  --image build/hotd1/maincpu.bin \
  --output build/research/hotdo-stream-decode.json
```

The default original-data check requires both g++ and clang++; repeated
`--cxx` arguments choose explicit alternatives. Metadata is in
`docs/reports/hotdo_stream_decode.json`. Passing is not a complete Model 2C
or arcade boot; [the completion gates](MODEL2C_DEFINITION_OF_DONE.md) are unchanged.
