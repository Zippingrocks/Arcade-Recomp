# ArcadeRecomp development plan

The target for the first major public release is an independently developed, faithfully playable, **native ahead-of-time recompiled** The House of the Dead (original Sega Model 2C arcade version). A native wrapper around an emulator does NOT fulfill that goal.

## Sequential milestones

1. **M0 — Authenticity and ROM layouts (in progress).** Original `hotdo` as the default reference, exact chip hashes, reproducible ROM region construction, trust boundaries, synthetic test vectors. Real user-supplied archive validation still pending.
2. **M1 — Intel i960KB.** Independently document instruction encoding, exception model, CPU state, memory semantics, branches, and execution traces; write a tested decoder and compile basic blocks to native machine code.
3. **M2 — Model 2C platform.** Establish authentic memory map, interrupts, bus timing, lightgun calibration, operator/test modes and FIFO transfers.
4. **M3 — Fujitsu MB86235 TGPx4.** Recover geometry processor instruction semantics, scheduling and command streams; develop a separate ahead-of-time translator and verify graphics command output.
5. **M4 — Sound and video.** Motorola 68000 sound program, Yamaha SCSP behavior, video timing, scene geometry, texturing and original raster effects.
6. **M5 — Faithful end-to-end gameplay.** All four chapters, dynamic routes, branching, cutscenes, bosses, enemy AI, gun accuracy, two players, endings and reproducible frame/audio capture validation.
7. **M6 — Alternate originals.** Revision A (`hotd`) then early `hotdp` prototype, preserving differences rather than silently folding historical versions into a remaster.
8. **M7 — Hardware expansion.** Additional Sega boards (notably NAOMI for HOTD2), then Chihiro HOTD3 and Lindbergh HOTD4 as distinct backends; evaluate each prototype in a documented chronology.

## Independent implementation rules

We may consult public manuals, known-accurate traces, observed behaviors, ROM wiring metadata, and other recompilers at a methodology level. Original code is developed in this project; no Daytona recompilation implementation is silently copied. Cite every substantial external technical fact.

## Stage gating

- No arcade fidelity claims until verified original-board reference traces or strong independent observations corroborate them.
- No 'recompiled' label until the target game program actually executes via ahead-of-time translated native code.
- No 'playable' label until meaningful gameplay runs through original content.
- No 'complete' label until full routes, sound, graphics, save/operator controls and edge cases are validated.
- Proprietary game ROMs/assets and ROM-derived memory images stay outside version control. All public tests use generated synthetic bytes.

See `PROVENANCE.md` for authoritative revision identifiers and evidence standards.
