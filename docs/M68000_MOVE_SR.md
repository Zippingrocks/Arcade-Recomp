# MC68000 MOVE immediate to SR

Status (2026-10-12): privileged immediate writes now cover every architected
CCR and interrupt-mask value that remains in supervisor mode with trace clear.
Trace entry and supervisor/user stack-bank switching remain explicit stops.

Motorola defines `MOVE <ea>,SR` as a privileged replacement of the complete
status register. For the current runtime, the safe executable destination
domain is:

- supervisor bit `S=1` (no USP/SSP bank transition);
- trace bit `T=0` (no unimplemented trace exception);
- any interrupt mask `I2:I0=000..111`;
- any five CCR bits; and
- every reserved bit zero.

`runtime/m68k_runtime.hpp` now accepts exactly that domain after proving the
current S bit known and set. Invalid destinations, unknown privilege and user
mode fail before changing SR, PC or the completion count. A native exhaustive
test covers all 65,536 immediate values plus current-state privilege and
knownness, and a generated test exercises the authentic `MOVE #$2200,SR`
instruction shape. The complete suite passes 759 tests in 205.519 seconds.

Across all 257 authenticated startup classes, the instruction completes and
execution then refuses at the following PC:

```text
completed instructions: 287064 / 287066 / 287067 by signature route
SR: 0x2200 (supervisor, trace clear, interrupt mask 2)
next PC: 0x00602170
stop: unsupported asynchronous-control state
```

The next instruction is already translated, but the runtime deliberately does
not execute it while interrupts are unmasked: SCSP pending/enable/level state
is not yet coupled to MC68000 autovector exception entry. Simply ignoring that
possibility would produce a false control flow. The next unit must implement
bounded interrupt sampling and exception entry (or prove no request can be
accepted at that boundary) before continuous startup advances.

No percentage changes: sound CPU remains 5%, SCSP/audio remain 0%, overall
HOTD1 remains about 10%, and Gates A/B/C remain open.
