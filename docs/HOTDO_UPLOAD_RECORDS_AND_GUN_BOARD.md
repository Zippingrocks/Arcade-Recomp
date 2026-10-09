# Original HOTD1 upload: empirical records and a specific FPGA lead

Date: 2026-10-09. Base: `a547fa5adfd2634405d34ef783a97f3a4efc4349`.

**Model 2C is NOT complete. No serial endpoint or FPGA configuration
format is being declared conclusively identified. Runtime device code and
the memory map are unchanged in this pass.**

## 1. The physical board is now tied to the game by Sega's own manual

Sega's original [House of the Dead Upright Operator's Manual](https://www.mamechannel.it/files_free/arcade_manuals_unpacked/hotd.pdf),
PDF page **57** (zero-based 56), lists part **837-12079** as the gun sensor
board. Its final wiring sheet, PDF page **59**, connects that board to
the game's **RS422** interface. Both pages were visually inspected rather
than relying on partial text extraction.

A [clear photograph of a board marked 837-12079](https://yatonarcade.com/cdn/shop/files/20240424144218.jpg?v=1713940965)
shows an Altera **FLEX** chip; the device marking is consistent with
**EPF8282A**. The seller's description is not being used to identify the
chip's logic or to establish the history of that particular board. The
photograph is evidence of the visible markings, not a schematic or an
execution trace. No copy of the photograph is redistributed here.

Altera's own [FLEX 8000 datasheet](https://www.farnell.com/datasheets/134632.pdf),
printed pp. **3–4 and 53**, documents SRAM-based configuration loaded at
startup and host-driven serial/parallel configuration. Altera's
[configuration-device handbook](https://www.farnell.com/datasheets/1558333.pdf),
Table **4–2**, printed p. **4–4**, lists **40,000 bits** for EPF8282A/AV;
its footnote on p. 4–5 says RBF files were used for those sizes.

The original HOTD1 upload is **40,960 bits**, not exactly 40,000. Its size
is close but **not a format signature or exact-length match**. No
explanation of the 960-bit difference is established here. Different
packaging, revisions or an entirely different receiver remain possible.

**Working hypothesis:** the game's 5 KiB upload may configure the FLEX
logic on the gun sensor board. The manufacturer wiring, observed chip,
host upload, and configuration-size scale make this a specific,
falsifiable lead. They do not yet show that the bytes reach that FPGA's
configuration pins, identify the bit-to-logic mapping, or prove its
response protocol.

## 2. New structure measured directly in the authenticated original bytes

Input: original `hotdo` main-CPU image, 2 MiB, SHA-256
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
The previously measured upload occupies `[0x000A3A00, 0x000A4E00)` and has
SHA-256 `de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.

The new metadata-only tool is `arcaderecomp.upload_framing`. It checks
both hashes and tests an **explicit empirical record model**, without
exporting the private upload or trying to execute it as CPU code.

| Observation | Measured result |
| --- | ---: |
| Upload length | 5,120 bytes |
| Zero bytes | 2,422 |
| Byte-distribution entropy | 3.829320270 bits/byte |
| Byte-stride scan | At phase 6 modulo 24, all 214 samples have their upper six bits set |
| Proposed data-record slice | 212 records × 24 bytes, beginning at upload offset 31 |
| Distinct records in that slice | 203 |
| Fixed bits in every proposed record | low bit 0; upper six bits 1 |
| Remaining middle field | 185 bits, with bytes interpreted little-endian |

The first 31 and final 1 bytes remain **uninterpreted**. The proposed
slice does not prove official preamble/header/trailer boundaries; a
long all-ones region could be framed differently. Every one of the 24
byte phases is reported, so the chosen phase is not presented without
its alternatives.

### An exact polynomial relation, including records withheld from derivation

For each proposed record, remove the fixed low bit and the six fixed high
bits. Interpret the middle 185 bits as a polynomial over GF(2). Using
**only the first 64 records**, compute the greatest common divisor of
pairwise differences against the first record. The resulting polynomial
is **`0x111`, or x^8 + x^4 + 1**. Each training record leaves residue
**`0xFF`** on division by that polynomial.

All **148 remaining records**, excluded from the divisor calculation,
leave the **same residue**. All 212 also pass the fixed-bit tests.

This is a reproducible mathematical relation in the original data, **not
an identified manufacturer CRC**. It does not determine the generator's
bit conventions, which bits carry logic versus check information, or
whether the physical FPGA verifies this relation. The records are not
independent random samples and the record model was selected after
examining the upload; no statistical confidence level is claimed.

The structure is consistent with framed configuration-like data and is
useful for comparing independently generated/captured candidate streams.
It does not recover a netlist, establish Altera format compatibility, or
supply a real serial-ready response. Altera AN33 was not successfully
retrieved during this pass, so it is not cited as proof of these record
boundaries or polynomial semantics.

## 3. Code, tests and actual regression results

New code: `arcaderecomp/upload_framing.py`. New tests:
`tests/test_upload_framing.py`. Saved original-input metadata:
`docs/reports/hotdo_upload_framing.json`.

- Baseline source archive SHA-256 matched the CI artifact digest.
- The current baseline completed **108** tests locally.
- Added **10** synthetic tests; the full updated suite completed **118**.
- Polynomial division is cross-checked against a separate bit-serial
  implementation across **800** generated cases.
- Mutation tests flip every one of the **192 bit positions** in a
  held-out synthetic record, detecting the change by the fixed-bit or
  residue checks; held-out corruption cannot alter the training divisor.
- Tests reject wrong image hashes, malformed sizes, invalid arithmetic,
  all-zero/all-one data and random data; the CLI cannot emit a successful
  report for a wrong original-ROM input.
- The generic structure function intentionally does not authenticate the
  unmodeled prefix. The original-ROM profile additionally requires the
  complete image and upload hashes. No universal FPGA recognizer is claimed.

The original `hotdo.7z` was re-audited: all **29** chip size/CRC32/SHA-1
fingerprints matched. The native startup was recompiled and actually run:

| Mode | Successful native steps | Deliberate halt |
| --- | ---: | --- |
| Strict default | 1,904 | IP `0xA375C`, write `0x01C00014` |
| Documented TX enabled | 1,910 | IP `0xA372C`, read `0x01C0001A` |

The TX-enabled run recorded channel 2 byte FF and channel 1 byte 01.
Both returned the expected diagnostic exit code **3**. No new fake status,
receive data, event backend, or unknown board-register handler was enabled.
This pass does **not** move the authentic-input startup boundary.

## 4. What this lets us test next

A known-good EPF8282A configuration generated from a small, controlled
logic design would allow an independent format comparison: record stride,
fixed bits, polynomial relation and length. Differential tiny designs can
then test which fields change with pin or logic assignments. A board
schematic or an original-cabinet capture correlating the host upload with
configuration-pin activity would independently test the recipient claim.
Neither experiment has been performed in this pass.

For a capture, the relevant named board is now supported by Sega's
manual, rather than inferred solely from a used-parts listing. The data
profile supplies exact baseline hashes and testable structural properties.
It **does not** justify driving configuration pins or changing voltages
without board-level electrical documentation.

`0x00F80000` still has its three known candidate stores and memory-test
context, but its physical function is not established. Nothing about the
FLEX hypothesis identifies that separate main-board address. Issue #6
remains open, as does authentic serial behavior in Issue #4.

## Reproduce, without publishing original game data

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp.upload_framing \
  --image build/hotd1/maincpu.bin \
  --output build/hotd1/upload-framing.json
```

The input must be reconstructed from a locally held, verified original
`hotdo` archive. The output contains only hashes, aggregate counts,
polynomial-model results and explicit confidence boundaries. No payload
bytes, disassembly, device programming file, HDL/netlist, or game binary
is committed.

See [the preceding upload experiment](HOTD1_SERIAL_UPLOAD_AND_MEMORY_TEST.md)
and [binding Model 2C completion criteria](MODEL2C_DEFINITION_OF_DONE.md).
