# Model 2C research notes — original HOTD1

**Status:** published board-map facts and independent observations; no full hardware runtime.

## Verifiable i960 address regions

The following preliminary CPU-visible address regions are documented in the MAME Model 2 machine driver. They are *reference facts* for an independently developed ArcadeRecomp bus — not borrowed implementation.

| CPU physical range | Preliminary role |
| --- | --- |
| 0x00000000–0x001FFFFF | i960 program ROM, 2 MiB |
| 0x00500000–0x005FFFFF | Shared working RAM, 1 MiB |
| 0x00800000–0x00803FFF | Geometry interface registers |
| 0x00900000–0x0097FFFF | Geometry buffer RAM, mirrored |
| 0x00980004–0x00980007 | Geometry FIFO status |
| 0x0098000C–0x0098000F | Video control registers |
| 0x00E00000–0x00E00037 | CPU control / wait-state configuration registers |
| 0x00E80000–0x00E80007 | Interrupt request, acknowledge and enable |
| 0x00F00000–0x00F0000F | Hardware timers |
| 0x02000000–0x03FFFFFF | Main game-data ROM window |
| 0x06000000–0x06FFFFFF | Additional ROM data window |

**Do not treat peripheral registers as generic RAM in a release build.** The first original HOTD1 startup routine at `0x000005F0` writes several configuration words to `0x00E00000`, the CPU control/wait-state register area. An instrumentation-only shadow-memory bus can capture those writes, but it does not reproduce genuine hardware timing or side effects.

All timings, interrupts, geometry FIFO behavior, lightgun calibration, and the complete Model 2C address mapping require further original research and tests.

## Component split

- **CPU core:** Intel i960KB; instruction addressing, register frames, interrupts and native translation.
- **Geometry:** Fujitsu MB86235 TGPx4; *separate* program and toolchain; geometry/FIFO cooperation with i960.
- **Sound:** 68000 audio CPU and Yamaha SCSP device. Distinguish native translation of code from modeling the peripheral.
- **Arcade I/O:** coins, gun triggers/coordinates, calibration, DIP/operator modes and board controls.
- **Video:** Model 2C-specific hardware pipeline, tile/text overlays and game presentation.

## Independently verifiable references

- Sega Model 2 driver (address-map and ROM wiring facts): https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp
- Intel 80960KB Programmer's Reference Manual (March 1988): https://www.bitsavers.org/components/intel/i960/80960KB_Programmers_Reference_Manual_Mar88.pdf
- Related Intel instruction description (HTML): https://manualzz.com/doc/7197351/intel-i960-ca-cf-microprocessor-user%E2%80%99s-manual

These references are cited for documented facts. ArcadeRecomp's translator is an original implementation and does not include MAME's emulator code or Daytona's recompilation code.
