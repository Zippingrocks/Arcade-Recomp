# Original HOTD1: raw input-polling contract recovered

Date: 2026-10-09. Initial research base:
`46bf7c757865a6bf0f8c463cf36ae61e3d097b34`.

Reconciled and revalidated against the concurrent CPU update at
`7c9ff60da5136f134bd57a79109f7c5ad777fb60`; no existing implementation
was replaced. The new findings and tests are additive.

**Status: isolated original native-code tests with synthetic replies.
Physical receiver, calibration and full Model 2C are NOT verified.**
No production device behavior or memory-map handler changes in this pass.

## What the original program actually decodes

The independently compiled original `hotdo` program contains a two-byte
helper at `0x000A3980` and a six-output polling routine at `0x000A38C0`.
Their selected static graph has 75 native-emitting instruction sites with
no unimplemented site in those two isolated roots. This is local coverage,
not coverage of the whole game or proof of CPU/hardware equivalence.

The pair helper combines two received bytes as:

```text
raw = low_byte | ((high_byte & 0x03) << 8)
```

Only two bits of the high reply are retained: the result is a raw 10-bit
value in 0..1023. The full polling routine invokes the helper for selector
pairs (0,1), (2,3), (4,5), and (6,7), then reads selector 8. Each selection
uses the existing register labels TX2/TX1: write a new selector through
TX2, send TX1 command 0, wait/read both RXs; send TX1 command `0x87`,
wait/read both RXs, and use the second transaction's RX2 byte as data.
These are observed host register operations, not a claim about the
receiver's physical wire format or internal UART organization.

### Six observed work-RAM destinations, in original write order

| Selector data | Host output rule | RAM address | Write width |
| --- | --- | --- | --- |
| 0 and 1 | low \| ((high & 3) << 8) | `0x0051EEF2` | 16 bits |
| 2 and 3 | low \| ((high & 3) << 8) | `0x0051EEF0` | 16 bits |
| 4 and 5 | low \| ((high & 3) << 8) | `0x0051EF0E` | 16 bits |
| 6 and 7 | low \| ((high & 3) << 8) | `0x0051EF0C` | 16 bits |
| 8 | (reply ^ 3) & 1 | `0x0051EF08` | 8 bits |
| 8 | ((reply ^ 3) >> 1) & 1 | `0x0051EF24` | 8 bits |

The last two fields invert the incoming low two bits independently. This
pass deliberately does **not** assign the raw words to physical player
axes or identify the flags as trigger/offscreen signals. That requires
additional callers, calibration logic and corroborated receiver evidence.
There are 9 selections, 18 transactions and 6 destination stores per full
snapshot. The pair helper returns through `0x000A39F0`; the snapshot
routine returns through `0x000A3974`.

## Exhaustive and adversarial isolated native tests

The input image is reconstructed from the user's original arcade archive,
not a PC/Saturn port. All 29 chip size/CRC32/SHA-1 records matched. CPU
image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.

The new `arcaderecomp.input_contract` first verifies that image hash,
generates private native C++ for the two original routines, and executes
`tools/experimental/hotd1_input_contract_probe.cpp`. That harness supplies
**explicitly synthetic** replies and readiness schedules and checks each
transaction, output address, output width and decoded result.

| Test domain | Cases per compiler |
| --- | ---: |
| Every low/high-byte pair, with two different RX1/acknowledgement distractor patterns | 131,072 |
| Full six-output snapshots with raw value, flag and polling variations | 4,096 |

The pair test covers all 65,536 byte combinations twice, including every
possible upper-six-bit pattern in the high byte. In the snapshot tests,
each raw slot visits all 1,024 possible values, all 256 flag-reply values
occur, and synthetic readiness delays of 0, 1, 3 or 7 polling reads are
used. These 4,096 snapshots are structured test cases, **not** the entire
Cartesian product of four raw input values and every reply sequence.
RX1 and first-transaction RX2 acknowledgements deliberately differ from
the data replies, detecting accidental reuse of those values.

**GCC and Clang produced identical reports. Clang ran with
UndefinedBehaviorSanitizer enabled.** The snapshot successful-instruction
counts range from 276 to 1,032 under those artificial poll delays. They
are not real device cycles, latency or timing measurements. Isolated root
returns have no caller in the harness; the expected `return_without_caller`
stop is checked rather than mislabeled as a normal complete arcade boot.

## New tools and independent tests

- `arcaderecomp/input_contract.py`: bounded JSON validation, original-image
  hash guard, private temporary native build, metadata-only output and
  refusal to overwrite the input image.
- `tools/experimental/hotd1_input_contract_probe.cpp`: host-contract oracle;
  no peripheral implementation and no autonomous physical-device replies.
- `tests/test_input_contract.py`: 9 tests using entirely artificial
  instruction streams and fabricated data. A separate synthetic assembler
  exercises the whole oracle; deliberate changes to high-byte masking,
  flag polarity and selector order must make the probe fail without
  emitting a successful report. Report tests reject missing domains,
  duplicate fields, wrong types, false declarations and wrong image hashes.
- `docs/reports/hotdo_raw_input_contract.json`: aggregate measured metadata,
  no upload payload, game instruction bytes, full disassembly or assets.

Initial baseline: 127 tests; first updated suite: 136 passed. A concurrent
CPU update then added ten existing tests. After reconciling, the complete
local suite passed **146 tests**, in two batches of 54 and 92 after a
monolithic run reached its external time limit. Both original-input
compiler experiments and strict startup were rerun against that combined
source, not just against the earlier working copy. The new original-ROM
experiment is separate from the synthetic-only public tests.

## Strict original startup has not been bypassed

The actual original startup was regenerated and compiled after these
additions. The default strict run again executes 1,904 instructions and
halts at IP `0x000A375C`, disabled serial TX at `0x01C00014`. With only
documented TX enabled, it executes 1,910 instructions, records TX2=FF and
TX1=01, and halts at IP `0x000A372C` reading unavailable status
`0x01C0001A`. Both return diagnostic code 3. No new reply/status fixture
was enabled in those regressions, and no unknown board write was ignored.

The reconciled source produces 3,051 candidate addresses, 3,042
native-emitting sites and 9 unsupported sites. That improvement comes
from the separately committed concurrent CPU update, not from these
input tests. This pass recovers and tests another host-side contract,
not additional runtime instruction coverage or a playable build.

## What this resolves, and what it does not

We now know exactly how these original routines request and unpack four
raw values and two flags. A future receiver implementation or captured
reply stream has a concrete host contract to satisfy, with tests that can
detect bit-width, command-order and flag-polarity mistakes.

It does not identify the 5 KiB upload's official format or prove that it
configures the gun-board FPGA. The prior Altera FLEX hypothesis remains a
hypothesis; further manufacturer-document and candidate-file research in
this pass did not establish the missing format mapping. See
[the prior upload/board study](HOTDO_UPLOAD_RECORDS_AND_GUN_BOARD.md).
Nor does this isolate or identify the separate `0x00F80000` memory-test
board write. That address remains a strict unimplemented boundary.

Real serial initial state, endpoint responses, timing, physical axes/flag
assignments, calibration, IRQ delivery, geometry, audio and full gameplay
remain open. **Issues #4 and #6 stay open; Model 2C is NOT COMPLETE.**

## Reproduce with a private, verified original image

```sh
python -m unittest discover -s tests -v
python -m arcaderecomp.input_contract --image build/hotd1/maincpu.bin --cxx g++ --output build/hotd1/input-gcc.json
python -m arcaderecomp.input_contract --image build/hotd1/maincpu.bin --cxx clang++ --sanitize --output build/hotd1/input-clang.json
```

The image must be reconstructed from the original `hotdo` archive through
the existing hash-checked tools. Generated game-specific C++ is temporary
and private. These commands do not program physical hardware, launch the
full game or replace its receiver with an invented runtime device.

See [Model 2C completion criteria](MODEL2C_DEFINITION_OF_DONE.md).
