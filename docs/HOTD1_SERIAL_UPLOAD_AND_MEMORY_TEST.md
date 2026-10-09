# Original HOTD1 serial-upload and memory-test evidence

Date: 2026-10-09. Base commit: `93532cf5f4dc6ef75c0298ebdca3396df1ea5061`.

**Model 2C is NOT complete. This pass changes research tools, not the
production hardware model. Neither issue #4 nor #6 is declared solved.**

## A new host-side serial finding: a 5 KiB upload

Independent examination of the authenticated original `hotdo` i960 program
identified a byte-streaming loop at `0x000A384C..0x000A3870`. The routine
loads the beginning and end pointers `0x000A3A00` and `0x000A4E00`, reads
each byte, writes it to the register currently named TX2 (`0x01C00014`),
and writes command-like value `0x07` to TX1 (`0x01C00012`). It waits for
receive-ready status and reads both RX registers after each iteration.

This is a **5,120-byte block** from the original program image. Its SHA-256
is `de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.
Its actual type is **unidentified**. No claim that it is executable firmware,
FPGA configuration, or data for a particular physical device has been made.
The bytes themselves are not committed or exported by the research tool.

The observed command/data-like pairing is a property of the HOST program.
It is not proof of two independent physical UART channels, nor proof of
the receiver's framing or internal implementation. Existing TX1/TX2/RX
labels follow the published [315-5649 register inventory](https://github.com/mamedev/mame/blob/master/src/mame/sega/stv.cpp).

## Native test of the original routine, with synthetic input explicitly declared

`arcaderecomp.serial_contract` generates private native C++ for the isolated
routine at `0x000A3750`, compiles the new diagnostic harness and runs it with
constant artificial RX2 values 0..255, separately for RX1=0 and RX1=255.
Status is explicitly supplied as synthetic ready data. There are **512 cases
per compiler**. Both GCC and Clang produced identical metadata reports.

In every sampled run:

| Observation | Result |
| --- | ---: |
| Original upload bytes compared in-process with the source ROM range | 5,120 / 5,120 match |
| TX1 register writes | 5,132 |
| TX2 register writes | 5,125 |
| Reads of RX1 and RX2 | 5,132 each |
| Synthetic-ready status reads | 5,132 |
| Native successful instruction steps before root return | 89,199 |
| Isolated procedure's root return site | `0x000A38B8` |

The root return has no caller in this isolated harness; its expected
`return_without_caller` diagnostic stop is checked explicitly. No full
arcade boot or physical device success is implied by this procedure return.

Two non-upload command-data values depend on RX2: the original code first
clears bit 0 (`RX2 & 0xFE`), and later sets it (`RX2 | 0x01`). This was
checked across all 256 constant RX2 values. Other summarized control data
and the uploaded block stayed unchanged when switching the sampled RX1
constant between 0 and 255. This does **not** prove invariance over every
possible time-varying receive sequence, and it does not reveal which bytes
a physical cabinet would return.

The new summarizer rejects incomplete sweeps, duplicated input cases,
non-synthetic declarations, failed upload matches, malformed metadata and
unsupported changes in the command sequence. It recognizes mask formulas
only after checking the complete 256-value domain, not just selected bits.

**What this advances:** instead of modeling only the opening FF/01 writes,
we now have a reproducible host-side upload contract, a known private ROM
range and checksum, and exact receive-dependent bit operations. A physical
capture can be compared against these facts. No ready signal or endpoint
response has been installed in the strict game runtime.

## `0x00F80000`: memory-test context now identified from original metadata

The menu-pointer chain used near routine `0x00008B10` resolves to the title
**MEMORY TEST**. Its table at `0x00008AE0` contains **eight descriptor groups
and 17 descriptor records**. Their observed fields include test-address,
length, mask, selector/count and display-chip-designator metadata. Two
records intentionally have blank display labels; the parser does not
invent or inherit chip names for them.

The two additional stores to `0x00F80000`, at `0x00008B88` and `0x00008BA0`,
bracket calls into those memory-test routines. The first uses r7, which
nearby code initializes to 2; the second uses g14. This pass does not assume
an unverified constant value for g14, execute the memory-test screen, or
identify the actual board circuit.

Descriptor address fields range across main/other memory regions including
`0x00200000`, `0x00548000`, `0x00900010`, and graphics-related address ranges
`0x11000000..0x11400000`. These are **program-observed test descriptors**,
not proof that every field has been mapped to an authentic physical device.
The code reports them without silently extending the native runtime's map.

`arcaderecomp.memory_test_layout` follows and bounds-checks those pointer
tables, extracts chip identifiers rather than font/text assets, and checks
the three known absolute store sites against the original image. It refuses
other ROM hashes, invalid pointers, malformed labels and unterminated tables.

**What remains unknown:** whether the board write controls access mode,
caching, a gate or some other behavior. No watchdog or ignored-write
interpretation is justified by the memory-test context alone.

## Validation performed during this pass

- The downloaded source artifact's SHA-256 matched its GitHub CI digest.
- Local baseline: **96 tests passed** (the older headline of 94 did not
  include two already-present cross-compiler tests).
- Added seven serial-contract tests and five descriptor/parser tests.
- Updated full local suite: **108 tests passed**.
- The isolated ORIGINAL routine completed all 512 synthetic input cases
  with GCC and again with Clang, yielding identical metadata reports.
- Re-audited all **29 original chip files** successfully. CPU image hash:
  `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
- Recompiled the actual original strict startup: **1,904** steps to the
  disabled TX write, **1,910** with documented TX enabled to missing serial
  status. The expected diagnostic exit code was 3 in both runs, and the
  TX-enabled run recorded channel 2 FF, channel 1 01.
- The original two-root code graph remains **3,051 candidates / 3,025
  native-emitting sites / 26 unsupported**. This pass adds evidence rather
  than claiming new gameplay coverage.

## Reproduce with private, previously verified original ROM data

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp build --layout targets/hotd1/original.json --rom /private/hotdo.7z --region maincpu --output build/hotd1
python -m arcaderecomp.serial_contract --image build/hotd1/maincpu.bin --output build/hotd1/serial-contract-gcc.json --cxx g++
python -m arcaderecomp.serial_contract --image build/hotd1/maincpu.bin --output build/hotd1/serial-contract-clang.json --cxx clang++
python -m arcaderecomp.memory_test_layout --image build/hotd1/maincpu.bin --output build/hotd1/memory-test-context.json
```

The serial contract probe is under `tools/experimental` and explicitly
prints its synthetic-input warning. It creates no original game source or
binary in the public repo; private generated code is kept in a temporary
directory and removed. The JSON reports contain metadata, not the upload.

Issues #4 and #6 still require evidence for genuine serial responses and
physical board behavior. See [completion gates](MODEL2C_DEFINITION_OF_DONE.md).
