# Sega Model 2C CPU-side serial capture comparison

**Scope: comparison of CPU bus transactions, NOT a serial chip emulator, gun
board implementation, UART timing model, or physical authenticity proof.**

The original HOTD1 native startup writes TX2=FF at 0x01C00014, then TX1=01
at 0x01C00012, then stops at a required status read at 0x01C0001A.
Its serial-access trace marks the last byte as UNOBSERVED rather than zero.

The independent arcaderecomp.serial_access_compare module compares native
strict-boot serial_access diagnostics with an **externally supplied CPU-side
bus observation transcript**. It strictly checks address, direction, bus
width, ordered transaction ordinal, completion, and known value. The
comparator never supplies a device reply to translated game code.

## External observation format

The following is an INVENTED SYNTHETIC EXAMPLE, NOT measured hardware data:

    {
      "schema": "model2c-cpu-serial-capture-v2",
      "provenance": "synthetic",
      "source_note": "Demo only. Not observed on an arcade cabinet.",
      "capture_summary": {"total": 3, "retained": 3, "dropped": 0, "complete": true},
      "events": [
        {"ordinal": 1, "direction": "write", "address": "0x01c00014", "width": 1, "completed": true, "value": "0xff"},
        {"ordinal": 2, "direction": "write", "address": "0x01c00012", "width": 1, "completed": true, "value": "0x01"},
        {"ordinal": 3, "direction": "read", "address": "0x01c0001a", "width": 1, "completed": true, "value": "0x00"}
      ]
    }

The example status 00 is invented for comparator tests; it MUST NOT be
treated as a Sega status default. For an actually collected capture set
provenance to external_capture_unverified and describe the board, acquisition
method, and capture period in source_note. The tool can compare but cannot
authenticate a provenance label. Failed/uncompleted reads must have
completed=false and value=null. Attempted writes always have known values.

The input must represent **CPU physical bus accesses**, NOT serial-wire
RS-422 frames or reconstructed expected operations. These are different
measurement layers. Use the existing serial_wire parser for serial-wire
samples; it does not magically recover the CPU status-register read stream.
Transaction ordinals do not imply elapsed cycles, UART baud or device timing.

## Acquisition completeness (v2)

External captures must now contain an exact `capture_summary` object:

| Field | Required meaning |
| --- | --- |
| `total` | Integer count of all serial CPU accesses in the declared acquisition window |
| `retained` | Integer count of access rows retained, equal to the length of `events` |
| `dropped` | Integer count of accesses lost by acquisition/export, required to be zero |
| `complete` | Boolean declaring the selected window ended and exported completely, required to be true |

The counters must be nonnegative integers, not booleans or numeric strings,
and `total` must equal `retained + dropped`. Missing fields, incomplete
windows, loss, and counter/row mismatches are refused before comparison or
report replacement. Contiguous ordinals alone cannot detect a cut-off export.
These declarations are producer claims; a forged summary still cannot prove
cabinet provenance or physical timing.

Record the window boundaries and acquisition method in `source_note`.
Preserve repeated polling reads, failed transactions, and all serial CPU
accesses within that window. Do not filter to only ready statuses or expected
command replies. A complete selected window does not establish a complete
boot or playthrough. Missing CPU-side status observations cannot be recovered
from RS-422 wire bytes by guessing when the CPU read them.

Legacy `model2c-cpu-serial-capture-v1` inputs are intentionally refused.
Regenerate the export from acquisition records with documented completeness
and loss counters, or recapture if those records are unavailable. Do not
merely append a zero-loss summary to an old file with unknown completeness.

## Reproduction

After collecting native strict-boot text with --serial-tx and a real CPU-side
observation JSON:

    python -m arcaderecomp.serial_access_compare --native-log /private/strict-boot.log --observed-json /private/observed-cpu-bus.json --output /private/compare-metadata.json

The native input **must contain exactly one final**
`serial_trace_summary total=... retained=... dropped=... truncated=... limit=...`
record, produced by the strict boot probe. The comparator refuses logs
without this footer: otherwise a cut-off file with contiguous ordinals
could silently masquerade as a complete capture. It also refuses reported
dropped accesses, inconsistent counters, and access records after the
summary. Older native logs without a summary must be recaptured; do not
fabricate a footer to make an incomplete trace pass.

The report contains SHA-256 input fingerprints, counts, and discrepancy
locations/reason codes. It deliberately omits received/status byte values.
The output write is atomic and refuses to alias either input via path,
symlink or hardlink. Exact event order is required: no best-fit alignment,
interpolation, implicit status zero, or hidden skipped accesses.

Result/exit-code categories:

- 0: matches_supplied_observations. All provided transactions matched,
     but this is NEVER a cabinet-authenticity certificate.
- 3: diverged. Transaction identity, known values, lengths or unexpected
     acceptance/refusal differ.
- 4: implementation_gap or insufficient_evidence. In particular, if the
     real board supplied a status value while the native runtime halted at
     an UNOBSERVED read, the checker marks the missing implementation; it
     does NOT feed a fake result into the runtime.
- 2: malformed/unsafe input or incorrect provenance and schema.

Capture data must be independently sourced. Repairers report that genuine
HOTD boards require an operational gun sensor RS-422 link. They do not
provide a verified sequence of startup 315-5649 RX/status byte values:
https://forums.arcade-museum.com/threads/house-of-the-dead.430249/
https://forums.arcade-museum.com/threads/house-of-the-dead-model-2-c-crx-no-voltage-at-rom-board.503559/

Regression, entirely synthetic:
    python -m unittest discover -s tests -p test_serial_access_compare.py -v

No commercial original game image, derived translated code or fabricated
hardware response is committed. The authentic startup serial-status
boundary, interrupts, MB86235, graphics and audio remain unfinished.
