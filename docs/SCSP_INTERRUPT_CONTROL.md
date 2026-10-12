# SCSP interrupt control

Status (2026-10-12): the manual-defined sound/main CPU interrupt enable,
pending/reset and sound interrupt-level words are modeled, including explicit
timer request integration. This does not yet deliver an interrupt into either
CPU core.

The Sega SCSP User's Manual, section 4.2.12, defines eleven interrupt factors:
three external inputs, MIDI input, DMA completion, manual CPU request, timers
A/B/C, MIDI output and the per-sample event. `SCIEB`/`MCIEB` enable factors;
`SCIPD`/`MCIPD` retain pending factors regardless of enable; bit 5 is the sole
software-writable pending bit; and writing ones to `SCIRE`/`MCIRE` clears the
corresponding pending flags. Three eight-bit `SCILV` planes form the sound
CPU's 3-bit autovector level, with factors 8..10 sharing bit 7.

`runtime/scsp_interrupt_control.hpp` implements those contracts with separate
sound/main state and knownness:

- only the eleven defined bits are accepted for enable, pending and reset;
- enable writes establish all eleven factor bits;
- pending writes affect only manual-request bit 5; zero is accepted as the
  documented no-op;
- reset-one clears and establishes only the selected pending factors;
- the three level planes retain exact eight-bit values and knownness; and
- an interrupt is reported asserted only when both its enable and pending one
  are known—unknown power-on state is never treated as deasserted proof.

The bus's explicit SCSP sample tick transfers Timer A/B/C requests to factors
6/7/8 for both CPU targets. It does not advance on sound-CPU instructions and
does not inject an MC68000 or i960 interrupt.

Focused native tests exhaust all 65,536 SCIEB values; cover both targets,
manual requests, selective reset, every factor/level plane, invalid addresses,
reserved bits, unknown state and Timer A request integration.
The complete suite passes 757 tests in 205.497 seconds.

Across all 257 authenticated startup classes, the original program performs
seven interrupt-control writes, completes common-control initialization and
reaches a CPU control-state boundary:

```text
PC 0x0060216c: MOVE #$2200,SR
stop: unsupported control value
completed instructions: 287063 / 287065 / 287066 by signature route
```

The runtime currently accepts only the initializer's earlier `0x27xx` SR
write, so the documented supervisor-mode interrupt-mask change to `0x2200`
is the next real blocker. CPU exception/interrupt delivery, continuously
scheduled samples, synthesis and audible output remain absent. `audio.scsp`
stays at 0%, overall HOTD1 stays about 10%, and Gates A/B/C remain open.
