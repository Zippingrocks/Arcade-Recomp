# EPF8282: a candidate rectangular layout for eight LUT fields

Date: 2026-10-09. Main baseline: `890d50d862f19793ab12cb5b512a899494a3a40d`.
Tested implementation: `cd8cd767830be538a1dcfb1bd9f5376e17700f86`.

**Model 2C is NOT complete. This is a candidate bit layout supported by
one archival reference, not a recovered physical FPGA circuit. No game
runtime, serial response or board memory-map behavior changed.**

## New result

The decoded SOF configuration data of the non-Sega `testmux` design contains
one rectangular-layout candidate matching the abstract function classes of
all eight logic cells described in its archived compiler report.

The earlier unsuccessful scan sampled sixteen bits at a constant spacing.
The new scan also allows a rectangle: 2, 4 or 8 rows with enough columns to
select sixteen bits. It tests 580 distinct shapes from explicitly bounded
row pitches and column steps. For each shape it derives all possible uniform
signed cell strides consistent with the first and third reference cells,
without the former +/-512 cell-stride limit.

The search first compares cells 1, 2, 3 and 7. It finds **2,047**
shape/start/stride candidates matching their function classes. Requiring
the remaining cells 4, 5, 6 and 8, and prohibiting overlapping fields,
leaves **one candidate in this search domain**:

| Parameter | Measured candidate |
| --- | ---: |
| First bit in decoded SOF data | 22,138 |
| Distance between successive cell starts | 1,416 bits |
| Rows per 16-bit table | 8 |
| Bits per row | 2 |
| Distance between row starts | 177 bits |
| Distance between the two columns | 1 bit |

For zero-based cell and row indices 0..7, and column 0..1, the selected
configuration position is:

```text
22138 + 1416 * cell + 177 * row + column
```

Truth-table bit order in this hypothesis is `2 * row + column`.
The eight fields select 128 distinct bits, ranging from 22,138 to 33,290.
These are offsets in the previously decoded **37,524-bit SOF data vector**;
they are not established physical SRAM row/column addresses.

An exploratory NumPy gather-based implementation and the final standard-
library scanner independently produced the same full search results. The
final scanner uses parallel population counts only as a filter, then checks
every retained truth table against the complete Boolean equivalence class.

## Exactly what this supports, and what it does not

The reference classes, in report cell order, are a compound Boolean
function, AND4, OR2, buffer, buffer, constant, OR2 and buffer. Equivalence
allows input permutation, input negation and output negation independently
for each cell. Consequently, this match does **not** recover input-net
ordering, output polarity, register selection or physical routing.

The four extra cells provide checks within the **same archived design**.
They are not independent held-out compiler builds. The search is bounded
and informed by known structure, so uniqueness within it is not a
statistical probability or a universal proof of the layout. A controlled
recompile or a genuinely matched second design is still needed.

Reference repository: `fayaw/spearlegacyLLRF`, commit
`6a0d68153d731518f07e98762f82d25e042838a8`, directory
`spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/`.

- [testmux SOF](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.sof,v): Git blob `4bd945df501d848d9fc4fd512945336ec7c24fca`.
- [testmux report](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.rpt,v): Git blob `88deb079d565b038b1bc4a71e015fd324dddd3ab`.

Both internally identify `EPF8282ALC84-2`. The report lists eight fitted
cells in row B, column 1. Their shared archive location is not a substitute
for a controlled, matched compiler rebuild.

## A separate-design validation source was rejected

The `buff_with_clk.sof` internally names `EPF8282ALC84-2`, but its archived
[companion report](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/buff_with_clk.rpt,v)
names **EPM5130QC**, a different target. That report cannot validate this
EPF8282 logic layout. The verifier checks this mismatch explicitly.

This does not invalidate the earlier byte-for-byte SOF/TTF representation
mapping: those two programming files agree with each other. It invalidates
using this mismatched report to attribute physical logic meanings.

## Code, tests and reproducibility

- `arcaderecomp/flex8000_lut_tiles.py`: bounded rectangular search, exact
  candidate extraction, source-hash and device checks, metadata-only CLI.
- `tests/test_flex8000_lut_tiles.py`: **12 synthetic tests**, including
  independent scalar-oracle comparison, inserted positive layouts in both
  directions, corrupted validation fields, uniform negative controls,
  invalid geometry/padding, alias rejection and wrong-target rejection.
- `.github/workflows/epf8282-lut-tiles.yml`: downloads only four pinned
  non-Sega files, recomputes the search, rejects the mismatched report,
  and exports only metadata and the exact source revision.

Local full suite: **197 tests passed in 44.722 seconds**, up from 185.
[Research-branch full CI](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37995290401)
passed **197 tests in 51.958 seconds**. The separate
[reference audit](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37995290410)
also passed and reproduced the complete local per-shape results.
Its downloaded metadata artifact matched SHA-256
`856e7c0bc56326f88e2bba8bf042f4c01c649d4f000c6658c5bd0552e8c0a2d6`,
and the recorded code revision matched the tested commit.

```sh
python -m unittest discover -s tests -v
# Explicit network operation: four pinned NON-SEGA files, metadata output only.
python -m arcaderecomp.flex8000_lut_tiles --fetch-reference --output build/reference/tile-audit.json
# Optional private original-ROM coordinate extraction; NOT logic validation.
python -m arcaderecomp.flex8000_lut_tiles --image build/hotd1/maincpu.bin --output build/hotd1/candidate-coordinates.json
```

The original-ROM mode authenticates the full CPU image before applying the
candidate positions to the decoded upload. It can select 128 bits but
publishes none of their values and explicitly does not claim that their
HOTD1 functions are verified. No configuration payload, archived design,
Sega bytes, game-derived executable or recovered netlist is committed.

## Original-game regression and remaining work

All 29 original `hotdo` chips again matched their manifest fingerprints.
CPU image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
A fresh original-ROM native build reproduced:

| Mode | Successful instructions | Deliberate stop | Exit |
| --- | ---: | --- | ---: |
| Strict default | 1,904 | IP `0xA375C`, disabled TX at `0x01C00014` | 3 |
| Documented TX only | 1,910 | IP `0xA372C`, unavailable status at `0x01C0001A` | 3 |

The latter still records TX2=`FF`, TX1=`01`. Neither enables fictional
receive/status input. This pass does not advance authentic game boot.
The existing baseline CPU graph reports 3,042 emitting sites out of 3,051
candidates, with nine unsupported; that prior CPU work is not a new result
of this FPGA research.

Next evidence needed: matched independent/compiler-controlled logic
samples, resolved per-cell input/polarity and routing, then register,
clock and physical endpoint behavior. Actual serial replies/timing and
the separate `0x00F80000` board register remain unresolved. Issues #4 and
#6 remain open. See [completion gates](MODEL2C_DEFINITION_OF_DONE.md).
