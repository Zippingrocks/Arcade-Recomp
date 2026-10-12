# MC68000 memory CLR and postincrement

Status (2026-10-11): native AOT supports CLR byte, word and long for `(An)`,
`(An)+`, `(d16,An)`, absolute-short and absolute-long memory destinations.
Predecrement and indexed CLR remain unsupported. This extends instruction
semantics; it does not install sound RAM, accept unknown device accesses,
implement hardware exceptions or produce audio.

## Primary sources and transaction order

The independent decoder and native semantics follow Motorola's
[M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
printed pages 4-73/4-74 (CLR), 2-6 (postincrement) and 2-18 (absolute-short).
CLR writes zero, sets
Z, clears N/V/C and preserves X. The MC68000-specific note requires a memory
read before clearing. Successful postincrement adds the operand size, except
byte access through A7 adds two. Absolute-short addresses are sign-extended.

The [MC68000 User's Manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf),
section 2.4/Figure 2-6, supplies the ordinary long operand read organization.
Tables 8-1 and 8-6 corroborate two operand word reads and two writes for long
CLR memory. Section 5.1.3 reserves the indivisible read-modify-write bus cycle
for TAS; CLR's separate data transactions must not be treated as that cycle.

Long CLR's **write order is an exception** to ordinary forward word order.
The original Atari *Hardware Bugs & Warnings*, dated 26 April 1995, printed
page 6, explicitly identifies CLR.L as reversing its two 16-bit writes.
The [original manufacturer scan](https://asterick.github.io/jag-docs/sources/Other%20Documents/Original%20version%20of%20updated%20documents/HWBugs%20%28Atari%20Original%29.pdf)
was visually checked, including its date and copyright footer. It is not the
later community-maintained SoftRef transcription. Source PDF SHA-256:
`ed27cfacd366e98f3af67f27dbe6183e5f4bdeb4e17d750c7b694c811b06acde`.

Composing those specifications gives this implementation's data-transaction
sequence, where A is the initial physical address:

| Size | Ordered transactions |
| --- | --- |
| Byte | read8 A, write8 zero to A |
| Word | read16 A, write16 zero to A |
| Long | read16 A, read16 A+2, write16 zero to A+2, write16 zero to A |

This is a source-composed functional CPU contract, not a captured Sega bus
trace. Each transaction masks its physical address to 24 bits. Odd word/long
addresses stop before callbacks. Word accesses never degrade into byte
callbacks. `read16_discard` defaults to the strict normal word read; an
override must reproduce a documented read transaction and its side effects,
not skip an unknown access or invent its value.

## Diagnostic failure is not a hardware bus exception

Flags, An, PC, knownness and completed-instruction count commit only after
every transaction succeeds. A denied fourth long transaction therefore leaves
the low word cleared and the high word unchanged, while leaving CPU state
uncommitted. Successful reads and writes are not rolled back. Fault metadata
identifies the rejected word transaction, not merely the long operand base.

The generated step catches the refusal and latches `Stop::bus_access`;
another call performs no transactions. Do not manually clear the stop and
retry against the already changed device. Restore/reinitialize both CPU and
affected bus state for a new controlled experiment.

This is deliberately a diagnostic contract, **not** a claim that physical
MC68000 bus faults roll back address registers or CCR. Motorola's user manual
section 6.3.9 describes aborted activity and partial exception context, not
instruction rollback. Hardware fault-time An updates, BERR stack frames,
prefetch, interrupts and cycle timing remain unimplemented. The successful
An update wraps at 32 bits, independently of the physical 24-bit bus mask.

## Verification

```sh
python -m unittest discover -s tests -p test_m68k_clr_memory_native.py -v
python -m unittest discover -s tests -p 'test_m68k*_native.py' -v
```

All 27 sound CPU tests passed GCC/UBSan without skips, including the five new
ROM-free CLR tests. The new generated C++ also passed
Clang 19 syntax checking with `-Wall -Wextra -Werror`. Coverage includes all
78 accepted memory encoding forms, all 1,024 CCR value/knownness combinations
per form, source-address definedness, sign extension, alignment, physical and
register wrap, A7's byte increment, discarded word reads and strict bus widths.
Every transaction-refusal position checks unchanged CPU state, retained bus
effects and a stopped second step. An invented three-long loop checks CLR's
composition with LEA, MOVEQ and DBRA. Public fixtures contain no game bytes.

## Authenticated original-site evidence

The authenticated local `epr-19720.31`, SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`, has CLR.L `(A0)+` at
`0x0060019c`. Private native GCC/UBSan validation passed **4,096 synthetic
state cases**, plus all four refused-transaction positions.

An isolated original loop entered at `0x00600198` with explicitly synthetic
A0/D0/D7 and memory state completes **57,347 instructions**, clearing 28,672
synthetic longs before unsupported ANDI.B at `0x006001a6`. A strict provider
instead completes only the initial register instruction and refuses CLR's
first word read. No RAM map or initial RAM contents are inferred from this.

The vector-entry static graph now has **43 sites, 42 translated**, one
unsupported site at `0x006001a6`, and no traversal-limit hit. These supersede
the preceding load-stage counts, not any hardware fidelity estimate. Original
bytes and generated original-code artifacts stay private under ignored
`build/`.

Neither earlier sound boundary is bypassed: strict vector execution still
requires the SCSP access at `0x00100401`; the optional common-control model
still requires the unknown board write at `0x00400001`. Sound CPU and sound-ROM
execution estimates remain approximately **5% -> 5%**, audio **0% -> 0%**, and
original HOTD1 overall **10% -> 10%**. Gates A/B/C remain open.
