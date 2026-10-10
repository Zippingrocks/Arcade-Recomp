# Serial command/data capture and a bounded wire-comparison path

Date: 2026-10-10. Base commit: `15cf2c6aeb9dbde6ee97a8bccf8c2daf58c1c2e9`.

**Model 2C is NOT complete. This is an observer and offline comparison tool,
not a replacement serial controller or a new authentic-input boot result.**

## New external evidence, with its scope preserved

The author's [Model 2B serial protocol report](https://github.com/biggestsonicfan/m2-sdk/blob/f952efb0bf7445f2d2cee1c9a6cca93af4194106/docs/rs422-serial-protocol.md)
identifies TXD2 at `0x01C00014` as an outbound data latch and TXD1 at
`0x01C00012` as the command/strobe. It reports measurements on the TTL side
of the RS-422 transceiver: 2-Mbaud, 8-N-1, least-significant bit first,
idle-high, with command `07` preceding each data byte in the measured data
transfers. The report also explicitly leaves receive-direction validation
and per-byte acknowledgement work unfinished. Its source blob is
`e3c317644033c3dd84a1475e35413229be9a47b8`.

Those are the researcher's reported Model 2B observations, not measurements
made by ArcadeRecomp on Model 2C. No matching raw original-board capture was
obtained in this pass. The shared chip and matching register addresses make
the report relevant; they do not prove identical Sega wiring, baud, RX/ACK,
mode controls, or gun-board behavior. The original source implementations
were not imported. The new code is independently written from the documented
interface facts and checked against original HOTD1 host writes.

## A data-latch write is not independently counted as a command

`runtime/sega3155649_tx_capture.hpp` observes ordered byte writes. It tracks
the last explicitly observed data value and creates a snapshot when TXD1 is
written. Each snapshot records whether its data was newly written or retained
from an earlier command. A command seen before any data write retains an
**unknown** data value; reset of observation continuity does not invent zero.

The observer rejects invalid addresses and non-increasing write order before
changing state. Its ordering numbers are not hardware clock cycles. It does
not emulate a UART, latch-overrun policy, TX busy flags, RX buffers, interrupts,
FPGA pins, or responses. In particular, it does not reclassify the existing
provisional independent-channel event model as hardware-verified.

A separate explicitly named helper predicts the `07,data` byte pair supported
by the Model 2B report. It rejects other commands and unknown data. Retaining
a data latch in an observation is not proof of the wire encoding of a control
command; no such encodings are generated.

## Original HOTD1 experiment

The new isolated native probe runs the unmodified original routine at
`0xA3750` with **explicit synthetic ready status and constant RX values**.
The two sampled input pairs are `(RX1,RX2)=(0,0)` and `(255,255)`, separately
under GCC and Clang. These are four executions, not exhaustive time-varying
protocol coverage or an actual cabinet boot.

Each execution produced:

| Observation | Result |
| --- | ---: |
| Successful native instructions before isolated root return | 89,199 |
| TXD1 command/strobe writes | 5,132 |
| TXD2 data-latch writes | 5,125 |
| Commands without a fresh data-latch write | 7 |
| Commands with unknown observed latch data | 0 |
| Upload bytes matched against the original ROM | 5,120 |
| Conditional `07,data` upload representation | 10,240 bytes |

All four predicted upload representations have SHA-256
`6f3d6837489491782bcf548129fe14a5b5cb9f5febd52522d82628134cb25752`.
The upload's known ROM boundaries and SHA-256 are unchanged. This confirms
host-write ordering under the stated synthetic inputs; it does not validate
buffer persistence or timing inside a physical 315-5649.

### Why deleting every 07 byte is wrong

The actual 5,120-byte HOTD1 upload contains **ten payload bytes equal to 07**.
A naive filter deleting every byte equal to 07 from the framed representation
loses those ten legitimate data bytes. `unwrap_07_pairs()` checks command
positions only and preserves every payload value, including consecutive 07s.
This demonstrates a data-corruption trap; it is not an allegation about the
external researcher's actual host-reader implementation, which was not audited.

## Offline sampled-wire comparison

`arcaderecomp.serial_wire` reads raw digital samples (one byte/sample, a selected
bit per channel) and decodes an explicitly selected 8-N-1 profile. Baud, sample
rate, channel, polarity and upload start-frame are explicit arguments. It does
not choose them by searching for a matching answer. The selected upload window
must contain complete alternating command/data pairs.

The parser bounds file sizes and byte counts, rejects false starts, invalid stop
bits and truncated frames, and refuses silent resynchronization. Integer-rational
sample positions support non-integer samples/bit. The whole capture must begin
idle and contain complete frames; noisy captures need a separately justified
analysis, not a guessed resynchronization. There is no drift/jitter correction,
analog-edge analysis, break decoding, serial-port I/O or general .sr importer.

Results include capture and payload hashes, sample positions, counts and mismatch
status, never the upload bytes. A caller must label input `synthetic` or
`external_capture_unverified`; neither label becomes hardware verification merely
because its payload matches. CLI output is prevented from aliasing either input,
including through symlinks or hard links.

For the original-data test, the native predicted bytes were converted into an
**invented** 12-MHz/D4/2-Mbaud waveform. Decoding reproduced all 10,240 framed
bytes and all 5,120 payload bytes. These sample rate/channel choices exercise
the tool; they do not select Sega Model 2C wiring or measure board timing. The
synthetic waveform has no realistic handshake pauses and provides no RX data.

## A separate, unresolved clue for 0x00F80000

The SDK's [initialization source](https://github.com/biggestsonicfan/m2-sdk/blob/f952efb0bf7445f2d2cee1c9a6cca93af4194106/src/kx_init.s)
comments a write of 3 to `0x00F80000` as preventing main-RAM writes. This is a
useful **RAM-write-protection hypothesis**, not a primary board specification
or an identified circuit. The same routine subsequently copies initialized data
to RAM, so a literal interpretation as blocking all RAM writes is not justified.

Fresh decoding of the original HOTD1 startup shows it writes **2**, not that SDK's
3, at `0x6B4`. The earlier MEMORY TEST references also remain. Exact affected
regions, bits, aliases, access widths and side effects are still unknown. No
write-protection handler or ignored write was added, and issue #6 remains open.

## Validation and unchanged original-game regression

The baseline source artifact matched its advertised SHA-256
`dee7e1d4ab47d403d2b9ce5f01917d5e659850198d66427950f9ee05924d6679`.
The baseline passed 329 tests. This pass adds 17 test methods: four compiled
observer tests, eight sampled-wire/parser tests and five wrapper/probe tests.
The combined local suite passed **346 tests**.

Observer tests cover all 65,536 command/data pairs under GCC and Clang with
UndefinedBehaviorSanitizer and warnings as errors. The native probe also runs
an entirely invented program in CI, including retained latch data and rejected
output overwrite/missing-upload cases. Sampled-waveform tests cover all byte
values, inverted polarity, back-to-back frames and 4, 6, 6.5 and 7.5 samples/bit.

All **29 original hotdo chip files** matched size/CRC32/SHA-1. Reconstructed
maincpu SHA-256 remains
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
Fresh AOT generation retained 3,051 static candidates, 3,042 native-emitting
sites and nine unsupported sites. Fresh strict startup still executes **1,904**
instructions before disabled TX, or **1,910** with documented TX enabled before
missing status at `0x01C0001A` (IP `0xA372C`). Both end with deliberate exit 3;
the latter records TX2=FF and TX1=01. Those runs have no synthetic RX/status
provider and do not use the new observer as a device backend.

## Reproduce

```sh
python -m unittest discover -s tests -v
# Existing private, authenticated maincpu image; neither command fetches ROMs.
python -m arcaderecomp.serial_tx_audit --image build/hotd1/maincpu.bin --output build/hotd1/tx-gcc.json --cxx g++
python -m arcaderecomp.serial_tx_audit --image build/hotd1/maincpu.bin --output build/hotd1/tx-clang.json --cxx clang++
# An EXAMPLE profile, NOT an established Model 2C rate or channel:
python -m arcaderecomp.serial_wire --samples /private/ttl-samples.bin --expected-upload /private/upload.bin --sample-rate 12000000 --baud 2000000 --channel 4 --first-frame 0 --provenance external_capture_unverified --output build/hotd1/capture.json
```

The native audit uses temporary private inputs/outputs and emits metadata only.
No Sega bytes, generated game C++, raw capture samples, external source code,
or derived game executables are included in the commit. Authentic receive
responses, board wiring, FPGA acceptance/logic and `0x00F80000` remain unresolved.
