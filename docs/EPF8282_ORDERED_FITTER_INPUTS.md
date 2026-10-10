# EPF8282 candidate checked against ordered fitter inputs

Date: 2026-10-10. Baseline main: `ec3718e5371b6bfaeb2cbac5997eb8feecfe200e`.

**Model 2C is NOT complete. This pass changes research tools and tests only,
not the game's native runtime, serial responses or memory map.**

## New evidence: the archived fitter file records input-slot order

The earlier analysis compared eight candidate LUTs with the Boolean
expressions in `testmux.rpt,v`. Even after finding a common polarity rule,
it allowed an independent input permutation for every cell. That leaves
ambiguity that a broad function-class match cannot resolve.

The additional original compiler file `testmux.fit,v` contains seven
`LORAX2` records, each listing four ordered input sources for a cell. Those
sources are named cells, references to declared input pins, or `X` entries.
The eighth cell has a constant DFF data input and no LORAX2 row; this is
recorded explicitly, not turned into a physical-disconnection claim.

[Primary archived fitter file](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.fit,v).

We now resolve those recorded sources and express the already normalized
report equations in their explicit compiler-slot order. The parser checks
both fit-file device declarations, matching CHIP/INTERNAL_INFO names,
unique pin/slot definitions and identical report/fit compiler version and
build timestamp. It will not invent a missing signal, assign a value to X,
or assume that duplicated tied inputs can be checked over all 16 states.

## Measured result: one common slot order, no per-cell choices

The previous geometry and polarity were kept fixed:

- Candidate first bit 22138, cell stride 1416, eight rows, row pitch 177,
  column step 1; coordinates refer to the decoded SOF vector, not physical
  axes measured on silicon.
- Common address XOR 15 and output XOR 0, inherited from the previous pass.
- Candidate data come from the same exact non-Sega `testmux.sof,v`.

Of the **24 possible shared slot permutations**, exactly **one** matches
all eight candidate truth tables: **[0, 1, 2, 3]**. In this model,
`compiler_slot[j] = candidate_address_bit[j] XOR 1`, with no additional
stored-output inversion. Every one of the 16 truth-table positions in
each of the eight cells is compared exactly: **128 output-bit comparisons
per tested common order**, not merely a population/function-class test.

There is no independent permutation for each cell in this new test.
The seven explicit input-slot rows constrain the nonconstant cells. The
constant data function is checked as a constant table, but does not
establish any clock, register initialization or physical connectivity.
A metadata `connected_slot_count` counts only sources in a recorded row;
zero in a missing constant row does not certify absent physical wires.

**This validates the candidate more strongly within this archived build.**
It is additional evidence from a third file of the SAME design, not a
second independent design, fresh compiler build, reverse-engineered
routing-switch map or a recovered HOTD1 circuit. Target-compatible
additional builds are still needed to establish generality.

## Pinned reference execution and reproducibility

The worker fetches exactly three files from reference commit
`6a0d68153d731518f07e98762f82d25e042838a8` and checks complete Git blob IDs:

| File | Git blob SHA-1 |
| --- | --- |
| testmux.sof,v | 4bd945df501d848d9fc4fd512945336ec7c24fca |
| testmux.rpt,v | 88deb079d565b038b1bc4a71e015fd324dddd3ab |
| testmux.fit,v | 12bd9dc6ce31fb3c70bbedb1a6ce9322a40cb10e |

The first reference execution, at code `58021931944abd2f210e41807385e1bcbb38b5e2`,
completed in [GitHub Actions run 38039762567](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/38039762567).
The returned metadata ZIP SHA-256 was independently checked against GitHub's
digest `5023a7c5635f1b8962cacbcd438fc4f1b9527dd57aa26ebdc43537ae256b4b21`,
and the artifact's source-commit record matched. The pipeline exports
counts, coordinates and conventions only, never actual configuration
bytes, equations, truth-table contents or the reference netlist.

The measured identity permutation is now a CI regression assertion. If
it changes, CI fails rather than moving the coordinates or changing the
polarity rule to recover a pleasing result.

## Added code and tests

- `arcaderecomp/flex8000_fit_slots.py`: strict ordered-fitter parser,
  report/fit build-identity checks, source resolution and common-order test.
- `tests/test_flex8000_fit_slots.py`: 14 synthetic parser/inference tests.
- `tests/test_flex8000_fit_slot_mutations.py`: checks all 128 possible
  single-truth-entry mutations of an unrelated artificial eight-cell
  example. Each corrupted example must lose the exact shared-order match.
- `.github/workflows/epf8282-fit-slots.yml`: separately executes the pinned
  reference audit and keeps metadata-only artifacts.

The synthetic tests use independent direct Boolean and assignment-table
oracles. They cover known shared orders, symmetric ambiguity, per-cell
reordering conflicts, wrong device/build records, unresolved/tied slots,
all three input hashes, and absence of reference payloads in JSON output.

Baseline: 224 local tests passed. The added 15 tests bring the local suite
to **239**, with full-suite CI checked before promotion to main. No actual
MAX+PLUS II compilation, new controlled placement experiment, or hardware
execution is being claimed.

## Original ROM regression actually performed

All **29** original `hotdo` chip fingerprints matched again. Reconstructed
CPU image SHA-256 remains:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

A newly compiled strict probe from the preserved runtime produced:

| Mode | Successful native instructions | Intentional boundary |
| --- | ---: | --- |
| Default strict | 1,904 | IP 0xA375C, disabled TX at 0x01C00014 |
| Documented TX only | 1,910 | IP 0xA372C, unavailable status at 0x01C0001A |

Both returned expected diagnostic exit code 3. TX2 FF and TX1 01 were
recorded. These runs used no synthetic status or receive provider.
The unchanged current two-root graph has 3,051 candidates, 3,042 native
emission sites and nine unsupported sites, reflecting earlier CPU work,
not additional CPU coverage achieved by this research pass.

## Reproduction and remaining work

```sh
python -m unittest discover -s tests -v
# Explicitly fetch the three pinned NON-SEGA compiler artifacts:
python -m arcaderecomp.flex8000_fit_slots --fetch-reference --output build/research/fit-slots.json
```

Authentic FPGA routing, registers, clock behavior, gun-board replies and
serial timing remain unresolved. The separate `0x00F80000` board function
also remains unidentified. Passing these candidate-encoding checks does
not satisfy any complete Model 2C platform gate.
