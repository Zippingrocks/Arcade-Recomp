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


## HOTD1's first I/O initialization target (original ROM)

The independently verified original `hotdo` program contains a direct i960
`CALL` at **0x0000068C**, with target **0x000A3750**. At that destination,
the instructions begin with an address load of `0x01C00000`, followed by a
byte store of `0xFF` to **0x01C00014**. These are static ROM findings,
not a claim that an accurate hardware startup trace has reached this code.

The modern MAME Model 2C map documents `0x01C00000..0x01C0001F` as
the **Sega 315-5649 serial I/O controller**, with byte-lane masking.
Its serial-channel attachments are involved in lightgun input handling.
The older driver names some game-specific lightgun operations directly,
but the current device decomposition is a better starting point for an
independent hardware-interface specification.

**Progress consequence:** our strict native CPU bus now identifies this as
`serial_io` and throws `DeviceAccessFault` instead of treating the
register as generic RAM or always returning zero. A usable I/O implementation
requires separate documentation, device state-machine tests, and original
cabinet behavior measurements. Synthetic tests prove the fault boundary
works, **not** that the actual game is booting.

References:
- [Public ROM layout and Sega I/O chip map](https://github.com/mamedev/mame/blob/master/src/mame/sega/model2.cpp)
- [Independent strict bus](../runtime/model2c_bus.hpp)
- [Synthetic native bus test](../tests/test_model2c_bus.py)
- [Synthetic strict bootstrap integration](../tests/test_strict_boot_probe.py)

### Bus fidelity constraints

Only the following **partially modeled** CPU-visible regions are implemented
in `StrictBus`: original i960 program ROM; main work RAM; preliminary
backing storage for CPU wait-state control; and user-supplied main game-data
ROM. A second published data-ROM address window maps the upper 16 MiB
of the reconstructed data region.

**Every other hardware access fails closed.** The wait-state backing store
does not actually delay a CPU cycle. Reset contents and unaligned transfers
still need validation against original Model 2C behavior. Neither the bus
nor the current AOT translator constitutes completed board support.
