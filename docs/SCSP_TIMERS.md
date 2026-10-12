# SCSP timers A, B and C

Status (2026-10-12): the three manual-defined SCSP timer words at `0x100418`,
`0x10041a` and `0x10041c` are modeled with an explicit sample clock. This is a
bounded timer-register milestone, not complete interrupt delivery or SCSP
timing.

The Sega SCSP User's Manual, section 4.2.11, defines three 8-bit up counters.
Each has a three-bit prescaler control: values 0..7 increment once every
1, 2, 4, 8, 16, 32, 64 or 128 samples. Writing the count starts the timer,
and reaching `0xff` requests its enabled interrupt.

`runtime/scsp_timers.hpp` implements all three write-only words:

- only the documented 11 low bits are accepted; five reserved bits fail;
- an aligned word write establishes control/count, clears prescaler phase and
  prior request, and starts that timer;
- `tick_sample()` is the sole clock input, representing one explicit 44.1 kHz
  SCSP sample event—sound-CPU instructions never advance it implicitly;
- each prescaler is independent and reaching `0xff` latches a request; and
- advancement beyond `0xff` fails atomically until interrupt-clear behavior is
  modeled, rather than guessing wrap/reload semantics.

Native tests exhaust all 65,536 word values, all three offsets, every
prescaler cadence, independent phases, request transitions, strict opt-in,
reserved bits, invalid offsets, write-only access and the no-implicit-clock
contract. The complete suite passes 755 tests in 203.803 seconds.

Across all 257 authenticated startup classes, the original program writes all
three timers and reaches the next common-control word:

```text
PC 0x00600256: MOVE.W (A1)+,(A0)
denied write: 0x0010041e, width 2
completed instructions: 285119 / 285121 / 285122 by signature route
timer writes: 3
```

Address `0x10041e` is `SCIEB[10:0]`, the manual-defined sound-CPU interrupt
enable register. Interrupt enable/pending/reset/level registers, CPU interrupt
delivery, continuous 44.1 kHz scheduling, synthesis and audible output remain
absent. `audio.scsp` therefore stays at 0%, overall HOTD1 stays about 10%, and
Gates A/B/C remain open.
