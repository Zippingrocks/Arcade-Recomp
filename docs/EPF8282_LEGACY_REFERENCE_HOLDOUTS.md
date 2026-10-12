# Two additional EPF8282 format holdouts

Date: 2026-10-11. This is non-Sega archival compiler-output evidence,
**not original-cabinet evidence or recovered gun-board logic**. No runtime
device behavior or authenticity estimate changes. `gun.lut` remains an
estimated 40%, the gun subsystem 5%, and original HOTD1 overall 10%;
Gates A/B/C remain open.

## Result

The existing serialization transform passes two additional public designs,
`DIV_10` and `RCV_TRIG`. Both name **EPF8282LC84**, the older non-A device,
in their SOF container and both FIT target declarations. Neither may be
silently treated as the earlier `testmux` target, `EPF8282ALC84-2`.

For each pair the unchanged model verifies:

- 5,120 serial bytes and 212 records of 24 bytes;
- all 212 fixed-framing and empirical polynomial-residue checks;
- an exact match of every one of the 37,524 decoded SOF data bits;
- exact reconstruction of the TTF using its own explicit prefix/suffix.

The SOF v0 packet-17 data shape also agrees with the previously observed
profile. Container checksum semantics and prefix/suffix meanings remain
unverified. Matching serialization does not establish matching logic,
clock, register or routing encoding across chip generations.

| Reference | FIT timestamp | Placed cells | B1 placed cells |
| --- | --- | ---: | --- |
| DIV_10 | 04/26/96 00:47:36 | 5 | 1, 2, 3, 4, 5 |
| RCV_TRIG | 04/26/96 03:49:24 | 53 | none |

Both FIT files identify compiler version `6.1 02/28/96`. A shared archive
location and matching device name do not prove that a FIT and SOF were
produced by the same compile invocation. That limitation is explicit in
the output metadata.

## Fixed-coordinate observation, not fitted-equation validation

The audit imports the existing tiled candidate unchanged:

```text
22138 + 1416 * cell + 177 * row + column
```

No search is run and no coordinates or polarities are adjusted to fit these
references. The selected DIV_10 fields have these abstract properties:

| B1 cell | FIT assignment | Candidate field observation |
| --- | --- | --- |
| 1 | counter RCO | three-input AND NPN class |
| 2 | counter QA | buffer/inverter class |
| 3 | counter QB | depends on three inputs; otherwise unclassified here |
| 4 | counter QC | depends on three inputs; otherwise unclassified here |
| 5 | counter QD | depends on four inputs; otherwise unclassified here |
| 6–8 | no assignment | constant class |

NPN equivalence permits input permutation, input negation and output
negation; an AND-class observation does not identify actual input signals,
their order, or polarity. The output intentionally omits truth-table and
configuration values. RCV_TRIG has no B1 placements, and all eight fields
are constant. This is an unused-bank observation, **not a second successful
functional holdout**.

The promising counter association is not sufficient to predict fitted LUTs.
There is no companion RPT for either design in the pinned repository tree;
their GDF schematics are binary, and the referenced `74160.gdf` library
definition is absent. The NDB is a symbolic name/hierarchy table rather
than an explicit fitted Boolean-equation report. A generic 74160 functional
description cannot establish the compiler's internal next-state equations,
unused-state simplifications, or control-signal implementation.

This limitation comes from inspecting the pinned
[DIV_10 GDF](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.GDF,v),
[hierarchy file](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.HIF,v),
and [name database](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.NDB,v).
Those inspection sources are not among the six automatic audit downloads.

Accordingly the audit always labels this result
`held_out_logic_validation: NOT_ESTABLISHED`. It neither falsifies nor
proves the A-series physical-layout hypothesis. No fake serial status,
FPGA acceptance, gun inputs or board response is introduced.

## Immutable primary references

Repository `fayaw/spearlegacyLLRF`, commit
`6a0d68153d731518f07e98762f82d25e042838a8`, directory
`spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/`:

| File | Git blob SHA-1 |
| --- | --- |
| [DIV_10.SOF,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.SOF,v) | `a4b2eac2c87580a9a4e40f748aa9b7f5fb42ddfa` |
| [DIV_10.TTF,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.TTF,v) | `9558faece11a93b8d67788df0fa63c340d6a2b12` |
| [DIV_10.FIT,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/DIV_10.FIT,v) | `8966e1214219d26ba1807157d184889fc715cb63` |
| [RCV_TRIG.SOF,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/RCV_TRIG.SOF,v) | `6be86ddc1161fd104618f1cb5587b9a363ea2c5e` |
| [RCV_TRIG.TTF,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/RCV_TRIG.TTF,v) | `c128f6d2badf7b3d00894226d2a752ce19b83eaf` |
| [RCV_TRIG.FIT,v](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/RCV_TRIG.FIT,v) | `7583e3b60dcaad1acd1889fb3992974d004d77fa` |

Copies under `sla_orig`, `sla_sav08062003` and `sla_tst` have identical
blobs for these files; they are not counted as additional builds.

## Reproduce

```sh
python -m unittest discover -s tests -p test_flex8000_legacy_audit.py -v
# Explicit network read of six pinned NON-SEGA files; retained only in memory.
python -m arcaderecomp.flex8000_legacy_audit --fetch-reference --output build/reference/legacy-epf8282-audit.json
```

`flex8000_sram.parse_sof` continues to reject the non-A device by default.
Only the new research audit requests the explicit legacy opt-in, and it
still requires the exact observed device and unchanged size, data-header,
packet-bound and padding checks. Existing A-series readers are not widened.
The audit reuses the existing RCS parser, codec, framing checks, FIT guards,
NPN operations and candidate extractor rather than implementing substitutes.

Local validation: 12 new synthetic tests pass. The broader FPGA suite ran
148 tests with 28 native-compiler-related skips in the default Windows
environment. The explicit six-source reference audit passed. Its metadata
SHA-256 is `603723d68ab6788ebf21ebe053725f9cffd64c233646f48ce0df7fd9ff2c38c7`.
Output uses explicit LF newlines for a platform-independent fingerprint.
These observations do not substitute for full project/CI validation.

Next experiment: obtain or independently decode a matched fitted-equation
source for DIV_10 without using the observed candidate fields to choose
equations. The already-inspected fields cannot become a blind prediction.
Reserve an uninspected, matched A-series design for genuinely held-out
validation, freezing predictions before examining its candidate values.
The authentic Sega 315-5649 RX/status and gun-board wiring blockers remain
separate and unsolved.
