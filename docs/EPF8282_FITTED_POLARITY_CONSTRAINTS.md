# EPF8282 fitted-polarity constraints and reconciled probe tooling

Date: 2026-10-09 (America/Los_Angeles). Baseline main: `b117144282b4678f4f9d40cb6647765feda66663`.

**Model 2C is NOT complete. No production game-runtime code or authentic device replies changed in this pass.**

## Result: the fixed eight-cell candidate passes a stronger equation test

The preceding main-branch pass found one rectangular candidate matching all eight function classes in an archival `testmux` SOF/report pair. That allowed independent input negations, input permutations and output negations per cell. Matching a broad class alone does not establish actual input polarity or routing.

The new `flex8000_fit_constraints.py` reads the report's actual Boolean equations and four explicit inverted-output aliases. It preserves signal names beginning with `/` as names, not an implicit NOT operation. It parses only a bounded Boolean grammar; no Python eval or arbitrary report code is executed. DFF definitions supply their data expression only: clocks, clear/preset and sequential state remain unmodeled.

Two interpretations were tested without moving any candidate coordinate:

| Interpretation | Common conventions fitting every cell |
| --- | ---: |
| Expressions in logical report-signal names | 0 of 32 |
| Expressions rewritten using the report's explicit inverted-output aliases | **1 of 32** |

A convention consists of one common four-bit LUT-address XOR mask and one common output XOR bit. Per-cell input permutations remain allowed because routing is unknown; separate ad-hoc input/output inversions for each cell are not allowed by this test.

The surviving normalized convention is **address XOR 15; output XOR 0**. In the candidate table-index coordinates, complement all four address bits, with no additional inversion of the stored output bit. This is a conditional configuration-encoding finding, **not** proof of physical inverters or a recovered pin map.

The remaining per-cell input permutation counts are **2, 4, 4, 6, 6, 24, 4, 6**. Symmetric functions and unused inputs account for real ambiguity; the tool does not select one arrangement arbitrarily. Even the shared encoding being unique in this tested family does not make the underlying circuit unique.

### Fixed evidence and independent execution

Both files come from pinned non-Sega reference commit `6a0d68153d731518f07e98762f82d25e042838a8`:

- `testmux.sof,v`, blob `4bd945df501d848d9fc4fd512945336ec7c24fca`.
- `testmux.rpt,v`, blob `88deb079d565b038b1bc4a71e015fd324dddd3ab`.

Source location: [archival reference directory](https://github.com/fayaw/spearlegacyLLRF/tree/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid).

Candidate geometry was inherited unchanged from `b117144`: first bit 22138, cell stride 1416, eight rows, row pitch 177, column step 1. The worker checks the two complete Git blob identities before extracting or interpreting data.

[Initial reference run](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/38015253368), code `82f983c0ead28e5c9b29b5dec6fffc180ebd9a34`, completed successfully. Its metadata artifact SHA-256 was checked locally against GitHub's digest `0708c2ce68e69201fc664b459228e0f721805616bd07c3db4a90f45a157c87cb`; its recorded source revision matched. The workflow retains metadata, not the reference configuration, equations or truth-table contents.

**This is additional evidence from the SAME archival reference.** It is not a second design, a controlled compiler rebuild, original-board validation or confirmation of HOTD1's circuitry. The previous `buff_with_clk` report/SOF target mismatch remains disqualifying for circuit validation; nothing in this pass overrides it.

## Previous unpublished affine/coverage work reconciled

Publishing access is available again. The prior local patch's affine hypothesis module, shared corpus reader and 15 synthetic tests have been integrated without replacing the newer rectangular-tile scanner. The original 23-source probe plan stays intact; the stronger optional plan contains 26 ORIGINAL UNCOMPILED AHDL sources.

The older plan misses 22 pairs' joint activation and admits a demonstrated nonlinear false positive. Three new held-out functions close those pairwise gaps. Complete pairwise coverage still cannot exclude every nonlinear alternative. The affine analyzer tests direct, inverted and XOR-combined truth-entry hypotheses against held-out samples without refitting them, preserving ambiguous intercepts. The test suite includes 262,144 predictions for four known synthetic functions over all possible four-input truth tables. No real minterm compiler corpus was produced or claimed.

## Validation actually performed

- Current source artifact identity checked against its CI SHA-256 `ea3293f634717842defc3705283168a9ea25f734f1b18fdde621dc4d9feeaa38`.
- 12 new synthetic parser/convention tests passed locally.
- Combined full local suite: **224 tests passed** (197 inherited + 15 reconciled + 12 new).
- Synthetic tests independently check expression precedence, explicit versus name-only polarity, report target/alias guards, a tuple-based transform oracle, planted shared conventions, symmetric ambiguity, failed per-cell inversion tricks, input identity and metadata-only output.
- Re-audited the uploaded original `hotdo.7z`: **29/29 chip fingerprints matched**.
- CPU image SHA-256: `da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
- A freshly compiled original-ROM strict probe still executed **1,904 steps** before the disabled serial write, or **1,910 steps** with only documented TX enabled, stopping at `0x000A372C` on missing serial status at `0x01C0001A`. Expected exit 3; TX2 FF and TX1 01 were recorded.

Those regression runs used no artificial RX/status provider. The fitted-polarity reference experiment used no Sega configuration data. No ROM, original-game generated C++, executable game payload or external reference design was published.

## Reproduce

```sh
python -m unittest discover -s tests -v
# Explicit download of two pinned NON-SEGA reference files:
python -m arcaderecomp.flex8000_fit_constraints --fetch-reference --output build/research/fit-constraints.json
# Synthetic coverage counterexample; no FPGA compiler is run:
python -m arcaderecomp.flex8000_affine_probe --self-audit --output build/research/coverage.json
# Original source generation only:
python -m arcaderecomp.flex8000_affine_probe --plan build/research/uncompiled-probes
```

## Remaining gates

This pass narrows the candidate encoding but does not map routing switches, clocks, registers or physical pins, nor identify the `0x00F80000` device. A controlled same-target design corpus, verified fitter placement/routing, or independent circuit-level evidence is still required before promoting candidate bit meanings into a faithful runtime. Issues #4/#6 and the Model 2C completion gates remain open.
