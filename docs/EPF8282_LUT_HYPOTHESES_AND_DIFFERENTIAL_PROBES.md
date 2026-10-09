# EPF8282 LUT hypotheses and differential-probe tooling

Date: 2026-10-09. Original main-branch baseline:
`d62eedd0b5ac566f31c41b6a14b969375e8de994`.
Tested research code: `48914b9992e9ba00c0d54ca5e74075f3468ae2cc`.

**Model 2C is NOT complete. No actual EPF8282 LUT bit, routing switch,
clock network or hardware response was identified by this pass.**
This work records a negative reference experiment and adds tools to make
future bit-to-logic experiments falsifiable. The game runtime is unchanged.

## 1. Reference equations provide a test, not a guessed floorplan

The pinned non-Sega `testmux` compiler report specifies EPF8282ALC84-2
and eight fitted logic cells in row B, column 1. It includes fitted logic
equations: a four-input AND, an AND/OR combination, OR-like functions,
buffers and a flip-flop with a constant data input. The SOF at the same
archived basename also identifies this target. This archival association
is **not** a controlled recompile or a guarantee that every companion
report describes precisely the same configuration generation.

Sources at reference commit `6a0d68153d731518f07e98762f82d25e042838a8`:

- [testmux SOF](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.sof,v), Git blob `4bd945df501d848d9fc4fd512945336ec7c24fca`.
- [testmux fitted report](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.rpt,v), Git blob `88deb079d565b038b1bc4a71e015fd324dddd3ab`.

The new scanner converts those abstract Boolean functions into four-input
truth-table equivalence classes. It permits input negations/permutations
and output negation, but does not permit arbitrary, unconstrained bit
rewiring just to force a match. The class sizes are 192, 32, 48, 8 and 2
for the selected complex function, AND4, OR2, buffer and constant classes.

### Measured negative result

The complete 37,524-bit SOF data vector was searched with within-table bit
spacings **1, 2, 4, 8, 16, 26, 104, 106, 177, 208 and 212**. For each,
the scanner tests uniformly spaced logic-cell starts, with signed cell
strides from -512 through +512 excluding zero.

**None of those bounded layouts matched the selected four nontrivial
cell classes together. Consequently, none matched the full eight-cell
pattern.** The final module independently reproduced the exploratory
workflow's exact counts without changing the tested spacing domain.

This rules out accepting those particular candidate patterns on these
inputs. It does NOT prove that regular packing is impossible, that the
reference association is perfect, or that every LUT must occupy a direct
16-bit truth-table field. Fitter optimizations, bypass paths, differing
address-bit encodings and more complicated physical layouts remain possible.
The 212 programming records must not be relabeled as 212 logic cells.

[Research-branch reference audit](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37992382927)
passed. Its metadata ZIP was checked against GitHub's SHA-256
`a3257755df48e0ef4614472cd8c9ba4b2268c55edc30cab355c763175d7ab48d`
and its recorded code commit matched the tested revision. No reference
configuration bytes are retained by the workflow artifact.

## 2. Differential mapper delivered, real controlled corpus not yet available

`arcaderecomp/flex8000_lut_probe.py` adds a separate method for comparing
controlled compiler outputs instead of guessing a contiguous LUT layout.

The intended corpus contains sixteen single-minterm designs, one exact
repeat of the first design, and six held-out Boolean functions. For each
configuration bit, the analyzer asks whether its values across all sixteen
training builds match one truth-table bit, directly or inverted. It then
checks each candidate against held-out builds not used for discovery.

A candidate survives only if all supplied holdouts agree. Multiple matching
configuration positions remain **ambiguous**, rather than choosing one.
If repeated baseline builds differ, the analysis refuses to treat that
corpus as repeatable. All SOFs must match their supplied SHA-256 hashes and
the same embedded device/package. Missing samples, reused holdouts, malformed
padding, path escapes, wrong target files and output-over-input writes are
rejected.

**Even a unique correlation is not a recovered physical LUT.** Fixed pins,
placement, input ordering, compiler settings and routing must be separately
verified in fitted outputs. The mapper does not certify those controls from
a basename or source equation and never sets a recovered-netlist flag.

### Probe sources are ORIGINAL and UNCOMPILED

The `--plan` command produces **23 original AHDL source probes**, with the
same interface and explicit Boolean truth functions. They are not generated
FPGA configurations and do not contain Sega or archived third-party design
bytes. AHDL equations were checked against the requested truth tables by
independent test parsing, but **the sources have not been compiled using
MAX+PLUS II**. No pin/placement assignment is invented by the generator.

No compatible licensed compiler installation or controlled real minterm
corpus was available in this pass. The vendor's [current licensing FAQ](https://www.altera.com/support/support-resources/licensing/q-and-a)
requires a valid MAX+PLUS II license and distinguishes limited BASELINE
licenses from full-feature support. No software license was acquired or
bypassed here. We did not claim that a generated plan is a completed
compiler experiment.

## 3. Tests and original-ROM regression

- Local baseline: **170 tests passed**.
- **15 new synthetic tests** cover truth-table ordering, equivalence classes,
  inserted regular-layout detection, uniform negative controls, scattered
  and inverted bit recovery, training-only nuisance correlations, ambiguous
  duplicates, failed holdouts, failed repeatability, bounded SOF manifests,
  same-target guards and source/output protection.
- Full updated local suite: **185 tests passed**.
- [Full research-branch CI](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37992382906)
  also passed, separately from the pinned-reference audit.
- The synthetic mapper recovered all 16 deliberately scattered/inverted
  truth bits in its positive control and rejected/flagged the deliberately
  inconsistent or ambiguous controls. **These are synthetic controls, not
  discoveries in HOTD1's FPGA.**

The original `hotdo.7z` was again verified against all 29 chip fingerprints.
Reconstructed CPU image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
A fresh native original-ROM build reproduced:

| Mode | Successful native steps | Controlled stop |
| --- | ---: | --- |
| Strict default | 1,904 | IP 0xA375C; disabled TX at 0x01C00014 |
| Documented TX only | 1,910 | IP 0xA372C; missing status at 0x01C0001A |

Both probes returned diagnostic exit 3. The second logged TX2=FF and TX1=01.
No simulated RX/status provider or new physical FPGA behavior was installed.

## Reproduction

```sh
python -m unittest discover -s tests -v
# Explicit download of only two pinned NON-SEGA reference files:
python -m arcaderecomp.flex8000_lut_probe --fetch-reference --output build/lut-reference.json
# Original source generation only; this does not compile the 23 designs:
python -m arcaderecomp.flex8000_lut_probe --plan build/lut-probes
# Once a genuinely controlled private SOF corpus exists:
python -m arcaderecomp.flex8000_lut_probe --corpus /private/corpus/manifest.json --output build/correlations.json
```

The corpus manifest is a JSON object with `schema_version: 1` and a `cases`
array. Each case has exactly `role`, `truth`, `sof` (relative path), and
`sha256`. Training truth values are the sixteen integers `1 << n`; the
repeated case is `role: repeat, truth: 1`. Four to 32 distinct non-training
holdout truth tables are required; the supplied plan uses six. Input files
must stay under the manifest directory; output must be outside it. Example
shape, **not a real identity or a complete corpus**:

```json
{"schema_version":1,"cases":[
  {"role":"train","truth":1,"sof":"minterm_00/lut_probe.sof","sha256":"REPLACE_WITH_ACTUAL_HASH"}
]}
```

This example is intentionally incomplete and will be rejected if used as
an actual audit input. Preserve compiler version, constraints and fitted
routing evidence alongside the real corpus; those are not auto-verified.

## Remaining hardware work

The original configuration-data representation is still reversibly mapped,
but actual LUT locations, routing, register and clock behavior are not decoded.
Authentic serial replies/timing and `0x00F80000` remain unresolved. This pass
adds neither a decoded FPGA netlist nor a new playable boot milestone.
See [Model 2C completion criteria](MODEL2C_DEFINITION_OF_DONE.md).
