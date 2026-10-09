# Original HOTD1 upload: independent EPF8282 configuration-format match

Date: 2026-10-09. **Model 2C remains incomplete. No runtime device behavior was changed.**

## New result

The original 5,120-byte HOTD1 upload strongly matches the **Altera EPF8282 FPGA configuration format**, not merely an unidentified record stream. This conclusion now rests on a **complete independent compiler-output comparison**, rather than only fitting a pattern to Sega's data.

The non-Sega reference is `testmux` from `fayaw/spearlegacyLLRF`, pinned at commit `6a0d68153d731518f07e98762f82d25e042838a8`. Its Altera MAX+plus II fit report names `CHIP "testmux"` and **`DEVICE = "EPF8282ALC84-2"`**. The corresponding tabular programming output is retained as an RCS archive. Our independently authored parser reads the full head snapshot, not the revision numbers or later delta records.

Reference paths:

- [Compiler fit report](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.fit,v)
- [Tabular programming output](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.ttf,v)

The complete upstream Git blob IDs are verified before parsing: fit `12bd9dc6ce31fb3c70bbedb1a6ce9322a40cb10e`, tabular output `b497a84a8288d94771b3439c36e667cd93cd5b51`. The source files were read in the dedicated [reference-audit CI run](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37986507994); only metadata was retained. No reference design, private Sega payload or FPGA netlist was copied into this repository.

## Whole-stream comparison

The model was fixed **before** testing this independent reference: 31 prefix bytes, 212 records of 24 bytes, one suffix byte; each little-endian record has a fixed zero low bit, 185 middle bits, and six fixed high one bits. Polynomial division of the middle field uses the previously found divisor `0x111` and residue `0xFF`. Nothing was refitted to make the new reference pass.

| Property | Original HOTD1 upload | Independent EPF8282 compiler output |
| --- | ---: | ---: |
| Entire stream size | 5,120 bytes | 5,120 bytes |
| Prefix size | 31 bytes | 31 bytes |
| Prefix bytes | Identical across both streams | Identical across both streams |
| Record count and length | 212 x 24 bytes | 212 x 24 bytes |
| Fixed-bit check | 212 / 212 pass | 212 / 212 pass |
| Existing polynomial relation | 212 / 212 pass | 212 / 212 pass |
| Suffix size and value | One byte; identical | One byte; identical |
| Distinct record bodies | 203 | 48 |
| Entire payload identical? | **No** | **No** |

The different content and identical structural envelope are important: this is not the same game data rediscovered elsewhere. It is a comparison to a separately compiled logic design targeting a named FPGA device.

Original upload SHA-256: `de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.
Independent decoded TTF SHA-256: `2e76b3b19d861c6197e81aa619f4600595392586bcca7050b4d9c6b9392423c9`.
Shared prefix SHA-256: `92cf7e86a6e03d51b66ca34fcfae71617c105aa699e12bc4dcfb20ff1b078b2d`.

The reference metadata artifact itself was downloaded and verified against GitHub's SHA-256 digest `cb851b112fc801d7c74b7b1fa3b31b2e6819166d3b849c2572590886664cdbe3`. The original CPU image was then read **locally**, hash-checked as `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`, and its full upload was compared using the same locked function. The resulting metadata is in [the comparison report](reports/hotdo_epf8282_comparison.json).

## What this establishes—and what it does not

**Strong format-level identification:** the formerly unidentified upload is consistent with a real EPF8282 programming stream down to its complete framing, prefix, suffix and per-record polynomial relation. This substantially strengthens the FPGA-configuration interpretation beyond the earlier hypothesis.

**Likely recipient, not traced wiring:** the prior [gun-board evidence](HOTDO_UPLOAD_RECORDS_AND_GUN_BOARD.md) reports an EPF8282ALC84-4 on Sega Gun Sense Assy 837-12085. The independent reference targets the same FPGA device family with speed grade -2. Together these facts make the photographed gun-board FPGA a strong candidate. They do **not** prove the exact HOTD1 board wiring, serial-to-configuration path, or that every board revision uses the same arrangement.

**Not recovered logic:** the 185 middle bits have not been mapped into LUTs, routing switches, registers, pin assignments or a validated netlist. The polynomial relation is still an empirically verified relation, not a manufacturer-certified checksum specification. No FPGA simulator or replacement logic is operational.

**Not a solved handshake:** configuration completion timing, input/output pins, true receiver status and actual serial replies still need evidence. The strict runtime has not been given fabricated ready values. The separate `0x00F80000` board address remains unidentified.

## Code and validation

New independently written tools:

- `arcaderecomp/flex8000_compare.py`: bounded RCS-head/decimal-TTF parsing, exact blob identity verification, fixed-model whole-stream analysis, optional private original-ROM comparison, metadata-only output.
- `tests/test_flex8000_compare.py`: **11 new synthetic tests** covering malformed snapshots, decimal parsing, exact identity guards, full-record validation, fixed/body-bit damage, unmodeled header changes and failure without false evidence.
- `.github/workflows/epf8282-reference.yml`: separate read-only job fetching only the two pinned non-Sega primary artifacts. It never receives a Sega ROM and publishes only hashes/structural metadata.

The full [CI suite at code revision 766bdfb](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37986507945) passed **157 tests in 47.060 seconds**. The dedicated independent-reference run also passed. The 11 new tests passed locally; the local full-suite attempt reached the container time limit and is not counted as a completed local full-suite run. Existing concurrent input/CPU work was preserved.

## Reproduce

```sh
# Only public non-Sega pinned inputs; metadata out.
python -m arcaderecomp.flex8000_compare --fetch-pinned --output build/reference/epf8282.json

# Optional original-ROM comparison on the user's private mapped CPU image.
python -m arcaderecomp.flex8000_compare --fetch-pinned --image build/hotd1/maincpu.bin --output build/hotd1/epf8282-comparison.json

# Offline equivalent using locally held full RCS source files.
python -m arcaderecomp.flex8000_compare --ttf-rcs /private/testmux.ttf,v --fit-rcs /private/testmux.fit,v --image build/hotd1/maincpu.bin --output build/hotd1/epf8282-comparison.json
```

This pass advances independent identification of the configuration stream. The next useful technical step is mapping configuration records to actual FPGA logic or obtaining a pin-level configuration trace—not replacing the uploaded design with guessed serial responses. **No Model 2C completion gate is claimed.**
