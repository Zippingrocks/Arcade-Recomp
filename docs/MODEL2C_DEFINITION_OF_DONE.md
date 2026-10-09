# Sega Model 2C — Definition of Done

**Status (2026-10-09): IN DEVELOPMENT. NOT COMPLETE.**

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

## Current evidence, not a completion percentage

**94 automated tests pass** at source commit `e8b90f09554a78c13f4c25f9bf9b3d8ebc2553af` ([CI evidence](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/37918124810)). The original `hotdo` ROM is authenticated. The named multi-register transfer and shift implementation is complete within its documented functional scope (Issue #9); precise CPU fault/timing behavior and unrelated instructions are not complete.

The same two-root original static graph contains 3,051 candidates: 3,025 now generate native operations and 26 still stop. The 75 newly supported original instruction sites passed 450 isolated native checks with synthetic CPU/memory state. These counts do not measure completed gameplay or cabinet verification.

Continuous original-ROM strict execution remains at 1,904 steps before the disabled first serial TX, or 1,910 with documented TX enabled before the missing serial-status read. No new fabricated serial response is used in these regressions. The earlier 91,118-step second-stage experiment used explicitly fictional serial input and stopped at unknown board write `0x00F80000`; it is separate from authentic-input evidence. The isolated original Intel IAC/ICR tests likewise do not prove continuous startup.

The optional serial event model now derives ready bits from explicit observed buffer events and consumes received bytes. It does not establish actual Sega initial state, timing, gun inputs or endpoint replies. **Issue #4 remains open.** The address audit adds two diagnostic-context store candidates beyond startup at `0x00F80000`, but does not establish the physical circuit or its effects. **Issue #6 remains open**, and no no-op handler was added.

The Intel SYNLD/pin-role tests and opt-in board IRQ registers do not implement actual original-cabinet interrupt delivery. Real serial status, CPU fault/interrupt behavior, accurate device timing, geometry, rendering, sound and gameplay remain unresolved.

See [the three-target evidence report](THREE_TARGETS_VALIDATION.md) for test scope, limitations and reproduction commands. **None of Gates A, B or C is being declared complete.**

This is independent from the later original-versus-Revision-A and prototype milestones. Prototypes expand the preservation roadmap but are not prerequisites for authentic retail HOTD1 completion.
