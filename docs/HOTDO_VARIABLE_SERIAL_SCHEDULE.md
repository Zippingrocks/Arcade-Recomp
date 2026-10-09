# Original HOTD1 variable-reply and readiness experiment

2026-10-09. **Host-program research only; Model 2C remains incomplete.**
Runtime device implementations and the memory map are unchanged.

## What changed compared with the prior constant-input sweep

The prior native experiment held each synthetic RX value constant for an
entire run. This pass changes RX1 and RX2 from transaction to transaction
using 16 deterministic seeds. It independently delays their ready bits
with six delay pairs (measured in status polls, not hardware cycles), and
runs each case with and without varying the other six status bits.

The actual hash-verified original hotdo routine at 0xA3750 was compiled
into native C++ with the existing AOT compiler. No replacement uploader
was used. The 192-case sweep checks every transmitted upload byte against
original ROM range [0xA3A00,0xA4E00), inside the process without exporting it.

A second experiment executes the original waiter at 0xA3720 against every
one of the 256 possible constant status bytes, with a 128-instruction bound.
This is 448 original-native-routine cases per compiler, not 448 new unit
test methods and not 448 original-hardware runs.

## Measured results

Both GCC and Clang completed all 448 cases, producing identical JSONL
metadata. Clang also ran with UndefinedBehaviorSanitizer enabled.

- All 192 upload runs transmitted the exact 5,120 original bytes.
- All used 5,132 command transactions, with both receive bytes consumed
  before the following command. This is observed host ordering, not proof
  of two independent physical UART channels.
- The two feedback writes use RX2 from transaction indices 4 and 6,
  respectively: clear bit 0, then set bit 0. These are distinct changing
  reply samples, not one constant fixture reused through the whole run.
- Successful native instruction counts ranged from 89,199 (immediate
  readiness) to 366,327 (nine extra polls per transaction). These counts
  are not cycle timing or gameplay progress.
- Of 256 status values, 64 let the original wait routine return. Exactly
  those satisfy `(status & 0x0c) == 0x0c`. The other 192 did not return
  within the explicit 128-instruction test bound.
- Other status bits do not alter this wait decision, even where published
  chip inventories give them error or transmit-status names. This is a
  statement about this original host subroutine, not the physical chip.

**Consequence:** making the host pass this loop is not a receiver-validity
check. These experiments cannot certify that real gun-board configuration
succeeded or determine the bytes/status that physical hardware supplies.

## Implementation and validation

New files:
- `tools/experimental/hotd1_serial_schedule_probe.cpp`
- `arcaderecomp/serial_schedule.py`
- `tests/test_serial_schedule.py`

The Python runner checks the full original image and upload hashes,
requires complete experiment domains, rejects partial/duplicated reports,
and reports synthetic-input provenance explicitly. Nine synthetic tests
cover metadata corruption, missing cases, wrong image identity, changed
native outcomes and compiling the harness against a fake failing program.

Local source came from CI artifact 11617890430 for commit
`a547fa5adfd2634405d34ef783a97f3a4efc4349`; artifact SHA-256 matched
`2924573027fce53323a1351c4f4716830e2b574e24f4c3ebc2f7eaf3b84fe1d2`.
Its 108 baseline tests passed; the same local snapshot with these nine new
tests passed all 117. The newer main-branch upload-framing research at
`2e37a4835cc22c4b6a88198e439ffd42bbbbdb6d` is preserved, not overwritten;
its additional tests were not part of that local snapshot count.

Actual original-ROM input: all 29 chips matched size/CRC32/SHA-1.
Main CPU image SHA-256:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
Upload SHA-256:
`de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1`.

## Reproduce privately

```sh
python -m unittest discover -s tests -p test_serial_schedule.py -v
python -m arcaderecomp.serial_schedule --image build/hotd1/maincpu.bin --cxx g++ --output build/hotd1/schedule-gcc.json
python -m arcaderecomp.serial_schedule --image build/hotd1/maincpu.bin --cxx clang++ --sanitize --output build/hotd1/schedule-clang.json
```

No original payload, game-derived C++, executable or asset is committed.
Only metadata and independently authored research code leave local tests.

## Remaining hardware questions

The gun-board FLEX/FPGA hypothesis from the preceding research remains a
hypothesis. Searches in this pass located references to Altera AN33, but
attempts to retrieve that application note failed; it is not cited as
format proof. No independent known-good EPF8282A configuration was obtained
for a format comparison. Existing manufacturer-source references and
confidence limits remain in HOTDO_UPLOAD_RECORDS_AND_GUN_BOARD.md.

Neither real receiver replies/timing nor the physical identity/effects of
0x00F80000 are established by this experiment. The MEMORY TEST context of
that address remains a separate investigation. No no-op handler, fake
ready signal or inferred FPGA endpoint was added to normal execution.
Issues #4 and #6 remain open; **none of the Model 2C completion gates is
being declared complete**.
