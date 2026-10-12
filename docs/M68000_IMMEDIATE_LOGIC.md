# Native MC68000 immediate logic

Date: 2026-10-11. Scope: `ANDI`, `ORI`, `EORI` byte/word/long to all eight
data registers. Fixed instructions are translated ahead of time; there is no
runtime opcode interpreter. Memory and CCR/SR variants remain explicit stops.

## Primary architectural source

Motorola's [M68000 Family Programmer's Reference Manual](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf),
ANDI pp. 4-18/19, EORI pp. 4-102/103, ORI pp. 4-153/154:
opcode prefixes `02`, `0A`, `00`; size fields `00/01/10` select byte/word/long;
Dn mode is zero. Byte immediates use the low byte of the extension word,
words use one extension and longs use two. Results replace the selected
operand width; X is unchanged, N/Z follow the result, V/C clear. The separate
CCR/SR encodings are not data-register instructions. Source text and field
tables were checked; the online PDF screenshot service failed, so no visual
verification is claimed for this review.

## Unknown state remains unknown

The runtime's known-bit mask is diagnostic metadata, not extra hardware.
AND establishes bits masked to zero; OR establishes bits forced to one;
XOR preserves which bits are known. Unaffected upper Dn bits and their
knownness are preserved. N is known only when the sign bit is known.
Z is known false when any known result bit is one; otherwise it is known
only if the whole result is known. V/C become known zero. X value and
knownness stay unchanged. Unknown N/Z payload bits are cleared but never
marked known. A later branch or store still stops if its required state
is unknown. No bus provider or hardware register acceptance changed.

## Verification

`tests/test_m68k_logic_immediate_native.py` contains six ROM-free tests:

- All 72 operation/size/register forms, extension truncations, excluded
  addressing modes and reserved sizes.
- Every byte input/immediate pair for all three operations, plus wide
  boundary/pattern values, independent per-bit Boolean oracles, upper-register
  preservation and all four X value/knownness combinations.
- All 6,561 ternary byte states (each bit known zero, known one, or unknown),
  six immediates and three operations. All compatible concrete completions
  determine expected result/flag knownness; two unknown payload patterns
  verify that guessed payload bits never become evidence.
- Every possible single unknown bit in word/long operands, checked against
  both concrete input completions, including sign-bit and upper-bit boundaries.
- Known/unknown flag consumers, undefined stores, strict MMIO refusal and
  invalid helper/control-state preservation.

Focused tests pass native GCC/UBSan and strict Clang 19 syntax checks.
Clang syntax checks are not Clang runtime execution.

## Private original-byte evidence

The original sound chip authenticates against size, CRC32 and SHA-1
`1edaed489a3518ddad85728e416319f940ea02bb`. Its `ANDI.B` site at
`0x6001A6` passes 16,384 isolated native checks with synthetic CPU state.
An isolated entry at `0x60018C` derives its register setup from original
instructions and clears 28,672 longs in explicitly synthetic memory. It
completes 57,351 instructions, then **refuses** a byte write of `0x08` to
`0x400001` at `0x6001AA`. A strict provider refuses the first memory read
after four instructions. No synthetic memory is installed in the sound bus.

Four independent entries at `0x6001A2`, with supplied D0 bytes
`F0/78/3C/1E`, derive refused write values `08/0C/0E/0F`. These are conditional
source-value checks, not a real sequence of accepted board writes.

The supported static startup graph grows from 43/42 discovered/translated
sites to 48/47, next unsupported site `0x6001BE`. Graph reachability does not
model device acceptance. The optional SCSP-control bootstrap still stops
after 18 instructions at the earlier `0x60014C` board write; the default
strict probe remains blocked by SCSP access. No sound-board wiring, timing,
audio output or cabinet fidelity is established. Sound CPU estimate stays
5%, audio 0%, overall original HOTD1 10%; Gates A/B/C stay open.
