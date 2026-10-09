# Sega Model 2C — Definition of Done

**Status (2026-10-08): IN DEVELOPMENT. NOT COMPLETE.**

This is the project's binding rule for when we may announce:
> **SEGA MODEL 2C RECOMPILATION SUCCESSFULLY COMPLETED!**

We will **not** make that announcement because a ROM is identified, native instructions execute, a startup routine reaches a title screen, or the game looks visually plausible.

## Milestones: three intentionally different claims

### Gate A — Original HOTD1 main CPU recompilation operational
- Original `hotdo` Intel i960KB program executes through compiled host code (no runtime i960 instruction interpreter).
- Reset, local calls, spill/reload, interrupts and faults work for exercised paths.
- No silent unimplemented instructions, arbitrary hardware returns, or substituted gameplay routines.
- CPU state is verified with independent reference traces.

### Gate B — Sega Model 2C platform operational for original HOTD1
- Intel i960KB, Fujitsu MB86235/TGPx4, sound CPU, Yamaha SCSP, display, timers, interrupts, memory mapping and lightgun I/O interact correctly.
- Real game startup enters gameplay and outputs original game graphics/audio.
- Original Model 2C control behavior, not placeholder RAM or guessed device responses, drives progression.
- Arcade service/test mode and calibrated one- and two-player gun operation are working.

### Gate C — **Sega Model 2C recompilation successfully completed for HOTD1**
**Every criterion below must be independently verified:**

- [ ] The game is fully playable **start to finish** from independently ahead-of-time translated arcade code.
- [ ] All four original campaign chapters, optional branches, boss encounters, game-over and endings are tested.
- [ ] One- and two-player gun positioning, triggers, offscreen reload, hit detection and calibration reproduce documented arcade behavior.
- [ ] Geometry, backgrounds, text overlays, animation, timing, effects, palettes and video output are faithful to original arcade reference captures.
- [ ] Background music, sound effects, voice playback, mixing and timing are faithful.
- [ ] Coins, arcade operator settings, difficulty configuration and service/test mode are handled.
- [ ] No unknown instructions or stubbed essential hardware behaviors occur across all documented playthroughs.
- [ ] Cross-checked against original arcade evidence; mismatches, remaining uncertainties and deviations are recorded.
- [ ] Reproducible clean build and tests run in CI; a fresh installation can supply a legally obtained `hotdo` ROM locally and play independently of an arcade emulator.
- [ ] All original Sega ROM bytes/assets and ROM-derived binaries are kept out of the public source repository.

**A broader statement — “Model 2C platform is generally complete for other Model 2C titles” — requires additional cross-game validation.** Passing HOTD1 alone does not prove every feature of all Model 2C hardware implementations.

## Status conventions

| Status | Allowed meaning |
| --- | --- |
| RESEARCHED | Hardware specification or ROM provenance documented |
| IMPLEMENTED | Code committed, but tests or fidelity not yet verified |
| SYNTHETIC TESTED | Artificial instruction/device tests pass |
| ORIGINAL-ROM TESTED | Recompiler runs verified original bytes in local controlled tests |
| ARCADE REFERENCE VERIFIED | Original machine's behavior corroborated |
| COMPLETE | All Gate C criteria passed; any exceptions explicitly documented |

We will report clearly when Gates A, B, or C are achieved. **The exact success declaration is reserved for Gate C**, with links to actual test logs and a full-game validation report.

Current state: authenticated original `hotdo` ROM; **74 automated tests passing**; first 1,910 strict original-ROM native instruction steps measured to the serial-status device boundary. An **opt-in, explicitly simulated serial-input** experiment executes 91,118 translated original-program steps and enters stage two at `0x000006B0`, where the strict bus stops on unknown board write `0x00F80000`. Separately, a **real original-ROM `SYNMOV` at `0x000006D4` executes natively in isolation**, setting Intel KB internal ICR from `0xFF000000` to `0x0F0E0D0C` and advancing IP to `0x000006D8`. This isolated test does **not** bypass the unknown board write in the faithful runtime. The new BAL/BALX/BX instructions also pass separate synthetic native tests, without original-ROM coverage for those instructions. These are authentic early CPU-code results, **not** original-cabinet verification, finished i960 support, a playable game, or Model 2C completion. Intel 80960KB `SYNLD` native instruction and the INT0/IAC /
INT2/INTR / INT3/INTA pin-role decoder now pass synthetic tests. This only
decodes CPU-side register roles and synchronous memory completion; it does
**not** generate real interrupts, CPU exception frames, or arcade timing.
Real serial status, interrupt delivery, accurate device timing, geometry, sound and gameplay remain unresolved.

This is independent from the later original-versus-Revision-A and prototype milestones. Prototypes expand the preservation roadmap but are not prerequisites for authentic retail HOTD1 completion.
