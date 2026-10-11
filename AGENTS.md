# AI agent instructions — ArcadeRecomp (all subdirectories)

These instructions apply to **every AI or human contributor** working in this
repository. Read these files *before editing anything*:

1. [progress/hotd1.json](progress/hotd1.json) — current project-wide estimates,
   every subsystem, next blocker, history and future targets.
2. [docs/PROGRESS_TRACKING.md](docs/PROGRESS_TRACKING.md) — update commands and evidence rules.
3. [docs/MODEL2C_DEFINITION_OF_DONE.md](docs/MODEL2C_DEFINITION_OF_DONE.md) — binding Gates A/B/C and completion wording.
4. [docs/ROADMAP.md](docs/ROADMAP.md) — implementation order and excluded future games.

## Before changing code

Run `python -m arcaderecomp.progress status --tasks` and select the scoped
subsystem/ID. Inspect its `next` recommendation. For work on the original
HOTD1 arcade target, prefer the authentic 315-5649 receive/status capture
blocker; then Intel i960 faults/interrupts/FP, MB86235/TGPx4, graphics,
audio, lightguns and continuous original gameplay. Other work is permitted
when it is independently verifiable. Do not claim that the hardest blocker
is solved merely because synthetic tests pass.

## Mandatory progress review with EVERY substantive change

Any edit to `arcaderecomp/`, `runtime/`, `tools/`, `targets/`,
`tests/`, or GitHub Actions workflows **MUST** add a new dated, evidenced
entry to `progress/hotd1.json` in the same push/PR. CI enforces this.
Keep all earlier history entries exactly unchanged.

If a bounded task measurably changed:
```sh
python -m arcaderecomp.progress update --id cpu.floating --percent 45 \
  --evidence tests/test_i960_subr_native.py \
  --note "Expanded exact-subset native real32 coverage; authentic cabinet FP faults remain unsupported."
```

If the work does not justify changing an estimated percentage:
```sh
python -m arcaderecomp.progress review --id model2c \
  --evidence docs/SEGA_IO3155649.md \
  --note "Inspected serial status wiring; no independently verified RX/status data, so estimate stays unchanged."
```

**Do not increment percentages automatically.** Do not equate green tests,
code-line counts, static opcode coverage, synthetic fixtures, documentation,
the completion of a tiny scoped task, or emulator shortcuts with authentic
hardware fidelity. Reduce estimates if new evidence disproves assumptions.
Review major-area and overall estimates separately; they are not averages
of subtasks. A 100% scoped helper never establishes a 100% platform.

Record **specific source/test/CI evidence and remaining limitations** in
every history note. Use `python -m arcaderecomp.progress validate`. Follow
`docs/PROGRESS_TRACKING.md` for tracked IDs, percentage changes and report
format. When replying to the user, include the scoped task's estimated
progress and the project-wide ~10% baseline (or its latest manually
reviewed replacement), clearly labeled as estimates.

## Architectural and legal non-negotiables

- The target is original Sega Model 2C HOTD1 (`hotdo`). `hotd` Revision A,
  `hotdp`, HOTD2 and later platforms have **separate** targets.
- Native AOT game CPU and original board behavior are required. Never replace
  the game with an emulator shell, import proprietary ROMs/assets, commit
  ROM-derived executable game C++, or copy MAME/third-party source verbatim.
- Do not fabricate Sega 315-5649 ready values, RS-422 RX bytes, FPGA acceptance,
  geometry output, interrupt timing, or a successful playable boot.
- Unsupported behavior must stop explicitly. Real original-ROM instruction
  checks use private local input; public tests must be entirely synthetic.
- After code changes, run `python -m unittest discover -s tests -v` and
  confirm GitHub Actions CI. Do not promote failing work to `main`.
- Only claim "SEGA MODEL 2C RECOMPILATION SUCCESSFULLY COMPLETED!" after
  **all** independently verified criteria in Gate C are satisfied. Before
  that, Gates A/B/C remain visibly open and overall percent remains below 100.

## After each task

Report the relevant subsystem's **previous → current estimated percentage**,
the overall original HOTD1 percentage separately, proof level
(synthetic/original-byte/arcade-reference), exact commit and CI status,
and the next unsolved blocker. An unchanged percentage is an honest outcome.
