# Original HOTD1: serial upload mapped to SOF configuration data

Date: 2026-10-09. Main-branch base:
`f1fffb418b7139fecc550df75cce927a5ef91afe`.
Tested research code: `dbe5fbccf4b5f22ca4c7922c534658a27effb278`.

**Model 2C is NOT complete. This pass decodes the configuration-data
representation; it does not recover a logic netlist or implement hardware
responses. Production runtime and memory-map code are unchanged.**

## Result: a reversible mapping, not just a format resemblance

The earlier EPF8282 format identification has been extended into an exact
mapping between serial programming records and the raw configuration data
inside a compiler-generated SRAM Object File (SOF).

Two distinct non-Sega compiler-output pairs pass the same mapping:
`testmux.sof` / `testmux.ttf` and `buff_with_clk.sof` / `buff_with_clk.ttf`.
In both cases the mapped serial data equals the SOF data byte for byte.
Reversing the transformation, including recalculating the record check
fields, reproduces the complete 5,120-byte TTF stream exactly. Each SOF
itself names the target device as **EPF8282ALC84-2**.

The first pair was used to discover the mapping. The second was tested
with that mapping fixed; its different data was not used to refit the
record layout, bit order or check relation. These are two distinct designs
from one historical archive and toolchain, not two independent compiler
implementations or physical-device tests.

## Exact observed record layout

Number bits 0 through 191 in each little-endian 24-byte serial record:

| Bit positions | Count | Observed role |
| --- | ---: | --- |
| 0 | 1 | Fixed zero |
| 1 through 177 | 177 | Data matching the SOF configuration-data field |
| 178 through 185 | 8 | Check field determined by the empirical polynomial relation |
| 186 through 191 | 6 | Fixed ones |

The full serial stream consists of a 31-byte prefix, **212 records**, and
one suffix byte. Prefix and suffix are preserved but not interpreted by
this codec. The record count does not establish a count of physical logic
cells, a device floorplan or a one-record-per-cell mapping.

After removing the 15 overhead bits from each record:

1. Concatenate the 177 data bits from each record in serial order,
   taking each record's data least-significant bit first.
2. Reverse the **entire 37,524-bit vector** (`212 * 177`). Reversing only
   bytes or only the order of records is not equivalent.
3. Pack least-significant bit first into **4,691 bytes**, with the four
   unused high bits in the last byte zero.

That result is exactly the measured SOF configuration-data payload in
both reference designs. It is a data representation, not an executable
program and not an identification of the meaning of individual bits.

The exploratory comparison considered nine possible contiguous 177-bit
slices, forward/reverse record order and forward/reverse within-record
order. Only the slice beginning at bit 1 with both orders reversed matched
the entire reference data vector. The final verifier uses this fixed
mapping, rather than accepting whichever transformation happens to fit.

### Record check field

The previous relation remains fixed: division of the 185 middle bits by
`0x111` (`x^8 + x^4 + 1`) gives residue `0xFF`. Given the 177 data bits,
there is one 8-bit check field satisfying that relation. The codec computes
it through a bijective remainder lookup and verifies it during decoding.

This is an empirically measured encoding, not a manufacturer-certified
CRC algorithm specification. It is also not authentication: tests explicitly
show that a two-bit change separated by 12 positions can preserve the
relation, while every individual bit flip in a synthetic 192-bit record
is detected. Full ROM and reference-file identity checks use separate
cryptographic hashes.

## Manufacturer documentation corroborates the distinction

Altera's [Application Note 33, Configuring FLEX 8000 Devices, June 2000,
version 3.03](https://dtsheet.com/doc/1428177/application-note-33--configuring-flex-8000-devices-)
was read through its archived text transcription. On printed p. 65 it
explains that programming software adds formatting and synchronization
information to SOF data and generates other programming-file forms.
Printed p. 66 describes decimal TTF bytes and least-significant-bit-first
serialization. Printed p. 69 describes per-frame CRC checking.

Those statements support separating configuration data from transport
formatting. They do **not** specify our exact 177/8/7 split, global reversal,
polynomial convention, or HOTD board wiring. Those details remain measured
results of the pinned compiler-output comparison. No AN33 timing value
was installed as a guessed HOTD serial or configuration delay.

## Source provenance and the inconsistent companion FIT file

All four full RCS archive blobs are pinned to repository
`fayaw/spearlegacyLLRF`, commit
`6a0d68153d731518f07e98762f82d25e042838a8`, under
`spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/`:

| File | Exact Git blob SHA-1 |
| --- | --- |
| `testmux.sof,v` | `4bd945df501d848d9fc4fd512945336ec7c24fca` |
| `testmux.ttf,v` | `b497a84a8288d94771b3439c36e667cd93cd5b51` |
| `buff_with_clk.sof,v` | `224eeb4b8023f9fc0a16166f9e72d224ba32b57b` |
| `buff_with_clk.ttf,v` | `8230b4adf18606b955862280a4d6d50b4ef7a06e` |

Each archive's full head snapshot is revision 1.1. A new bounded binary
RCS reader handles escaped `@` bytes and refuses duplicate, missing or
malformed snapshots. Revision-like strings inside quoted logs/descriptions
cannot be treated as real entries. Older delta text is not applied.

The companion [buff_with_clk FIT head](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/buff_with_clk.fit,v)
names **EPM5130QC**, whereas that name's SOF embeds **EPF8282ALC84-2**.
Their common filename is therefore insufficient to establish a matched
build. This pass does not use that FIT's pin assignments or logic locations
to interpret the SOF. The second SOF/TTF pairing is supported by its embedded
device and exact configuration-data equality, not by the inconsistent FIT.

### Restricted SOF parser scope

The two measured SOFs are 4,820 bytes with seven tagged packets. Packet
17 is 4,703 bytes: a measured 12-byte header followed by the 4,691-byte
configuration-data vector. Its header contains the value 37,524. The
parser requires this profile and rejects invalid bounds, duplicates,
trailing data, wrong devices and nonzero unused padding.

Unexplained header fields are checked against the observed profile, not
given invented meanings. The SOF container checksum has **not** been decoded
or independently verified. Whole-file identity is established by the pinned
Git blob hash. No general SOF reader, full SOF writer or universal FLEX
configuration decoder is claimed.

## Applied to the authenticated original HOTD1 upload

All **29 original hotdo chip files** again passed the manifest's size,
CRC32 and SHA-1 checks. The reconstructed 2-MiB CPU image has SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

Its upload at `[0x000A3A00, 0x000A4E00)` remains 5,120 bytes, SHA-256:
`de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.

Applying the independently checked mapping yields the 37,524-bit vector
packed into 4,691 bytes, SHA-256:
`5144cf9b156a27a41e53e17a31aa6efb098fcce448fbf9eed1de9a1bc6733f09`.
Re-encoding it with the preserved original prefix/suffix reproduces every
byte of the original upload exactly, including all record check fields.

There is **no original Sega SOF file in this experiment**. The original
result is an application and roundtrip of the mapping validated on the two
non-Sega pairs, not a comparison with a recovered Sega development file.
Only hashes and structural metadata are published. No configuration bytes,
reference designs, game-derived C++, private game executables or netlists
were added to the public repository.

## Code and completed tests

- `arcaderecomp/flex8000_sram.py`: bounded binary RCS and restricted SOF
  readers; reversible serial/data mapping; empirical check encoding;
  hash-pinned reference verification and metadata-only original profile.
- `tests/test_flex8000_sram.py`: **13 new synthetic tests**, including an
  independent bit-by-bit packing oracle, an independent coefficient-array
  polynomial oracle, all 192 single-bit mutations, a deliberately undetected
  two-bit mutation, malformed containers and exact identity guards.
- `.github/workflows/epf8282-sof-discovery.yml`: final reusable reference
  audit, replacing the exploratory inline script. It fetches only the four
  pinned non-Sega files and retains only metadata and the source commit.

Baseline: **157 tests passed locally**. Updated suite: **170 tests in
42.231 seconds, exit 0**. The same code's [full research-branch CI run](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37988888019)
passed **170 tests in 51.718 seconds**. The separate [two-reference data
mapping audit](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37988888063)
also passed. The downloaded metadata artifact's SHA-256 was verified as
`7dce1d1e05d15032a6c875b5295043b651bcf56cf68a2d1737cb86cc63762470`,
and its recorded code commit matched the tested revision.

Fresh original-ROM native startup regression:

| Mode | Successful steps | Deliberate stop | Exit |
| --- | ---: | --- | ---: |
| Strict default | 1,904 | IP `0xA375C`, disabled serial TX write `0x01C00014` | 3 |
| Documented TX only | 1,910 | IP `0xA372C`, unavailable status read `0x01C0001A` | 3 |

The latter records TX2=`0xFF`, TX1=`0x01`. Neither run enables synthetic
receive/status providers or changes the unknown-board-register policy.
These diagnostic stops do not constitute a successful arcade boot.

The measured results and exact source identities are retained in
[the metadata report](reports/hotdo_sof_data_mapping.json).

## Reproduction and next unresolved layer

```sh
python -m unittest discover -s tests -v
# Explicit network operation: only the four pinned non-Sega artifacts.
python -m arcaderecomp.flex8000_sram --fetch-pinned --output build/reference/sof-data-mapping.json
# No network required; authenticated original data stays private.
python -m arcaderecomp.flex8000_sram --image build/hotd1/maincpu.bin --output build/hotd1/sof-data-mapping.json
```

The remaining FPGA layer is the meaning of individual configuration bits:
LUT contents, registers, routing switches, pin connections and reset/clock
behavior. Controlled, matched compiler builds or an independently verified
bit-to-resource map are needed to establish those meanings. A reversible
file-format mapping alone does not supply them.

Actual gun-board wiring, configuration completion, serial reply values and
timing remain unverified. `0x00F80000` remains separately unidentified.
Issues #4 and #6 remain open. **No Model 2C completion gate is claimed.**
See [the binding completion criteria](MODEL2C_DEFINITION_OF_DONE.md).
