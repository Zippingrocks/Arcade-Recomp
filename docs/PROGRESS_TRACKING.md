# Progress tracker and rules for every contributor

**The authoritative project-wide estimate is**
[`progress/hotd1.json`](../progress/hotd1.json).
It exists so Codex, Claude, other AI coding agents, and humans see the same
baseline and must review progress when changing the repository. Root
[`AGENTS.md`](../AGENTS.md) points to this file and the required workflow.

## Interpretation and baseline (October 10, 2026)

| Original HOTD1 area | Initial estimate |
| --- | ---: |
| Authenticated ROM identification and reconstruction | ~95% |
| Intel 80960KB native AOT CPU | ~55% |
| Sega Model 2C motherboard/bus/serial/IRQ | ~20% |
| Functional gun-sensor board and Altera FLEX | ~5% |
| MB86235/TGPx4 geometry and Model 2C video | ~0% |
| Motorola 68000/Yamaha SCSP audio | ~0% |
| Authentic end-to-end game execution/playthrough | ~0% |
| Tooling, reverse engineering and automated validation | ~85% |
| **Faithful original HOTD1 native PC port (subjective overall)** | **~10%** |

The JSON also records **85 individual tasks across eight areas** and **six
follow-on targets** (Revision A, prototype, other Model 2C games, NAOMI,
Chihiro, Lindbergh). Those targets **do not** reduce original HOTD1's overall
percentage, which is a separately reviewed subjective estimate, NOT an
arithmetic average of components.

Percentages were rounded by engineering judgment. They are not factual
completion measurements, not an automated estimate from tests/code coverage,
and not proof of cabinet accuracy. A scoped subtask may be 100% while the
relevant parent hardware area is 20% or less. The historic 3,042/3,051 static
candidate decode result is not 99.7% game or CPU completion. Passing 432/432
baseline tests shows that tested implemented behavior passed—nothing more.

## Inspect progress and the next blocker

```sh
python -m arcaderecomp.progress status
python -m arcaderecomp.progress status --tasks
python -m arcaderecomp.progress status --json
python -m arcaderecomp.progress validate
```

Each area has a stable `id`, manually estimated `percent`, and a `next`
item describing an actionable blocker. The detailed `area.task` IDs include
CPU faults/rounding, authentic 315-5649 serial RX, MB86235, SCSP, guns,
four chapters, original-ROM auditing, FPGA research, CI and more. These
stable IDs must not be silently renamed or deleted.

## Update after **every substantive source/test/tool/workflow change**

**If an estimate actually changed** and you can cite specific work:

```sh
python -m arcaderecomp.progress update --id cpu.floating --percent 45 \
  --evidence tests/test_i960_subr_native.py \
  --note "A specific new exact real32 instruction case passed native parity, but correct i960 FP faults remain unimplemented."
```

**If the change did not justify a percentage change**, create a review entry:

```sh
python -m arcaderecomp.progress review --id model2c.authentic_rx \
  --evidence docs/SEGA_IO3155649.md \
  --note "Reviewed register evidence and native telemetry; independent cabinet RX/status values are still unknown."
```

Run `python -m arcaderecomp.progress validate` and the full test suite.
Both commands append a dated, auditable history entry with the task/area ID,
prior/new percentages, evidence and explanation. Edits to current
percentages without consistent history fail validation. Changing multiple
independently affected task/area/overall estimates requires separate
`update` calls and explanations for **each** change. A lower estimate is
allowed and appropriate when new information invalidates prior assumptions.

The `--evidence` flag can be repeated; use a real relative source/test/doc
path or a GitHub commit or Actions URL. Notes should identify implementation,
validation type, and remaining uncertainties. Do not label synthetic tests as
arcade hardware observation. Never guess completion solely because a feature
was implemented. Only advance a parent area or overall project if its
*broader* acceptance criteria now justify a manually reviewed revision.

## CI enforcement

`.github/workflows/tests.yml` validates the JSON and executes the
progress-history guard. Any changed source in `arcaderecomp/`, `runtime/`,
`tools/`, `targets/`, `tests/`, or `.github/workflows/` requires a
**changed** `progress/hotd1.json` containing a new **append-only** history
entry. There is no automatic percent adjustment. Unchanged progress is
recorded with `review`. This guard complements, not replaces, the normal
GCC/Clang native/synthetic test suite. Docs-only editorial updates are
encouraged to use the tracker but are not automatically blocked.

The CI guard may be tested locally using two git revisions:

```sh
python -m arcaderecomp.progress_guard --base HEAD~1 --head HEAD
```

For pull requests, the CI compares the pull request base with HEAD. For pushes,
it compares the previous SHA with HEAD. History edits/deletions fail. Historical
baseline commit and CI fields describe the original estimate's evidence
checkpoint; they should not be automatically rewritten to pretend a newer
test run validated older claims. Later evidence belongs in the history.

## Completion gates and proof levels

The binding criteria are in
[`MODEL2C_DEFINITION_OF_DONE.md`](MODEL2C_DEFINITION_OF_DONE.md).

- **Gate A**: original HOTD1 i960 AOT execution including fault, interrupt
  and exercised CPU-state correctness; **not yet met**.
- **Gate B**: complete original HOTD1 Model 2C platform interaction, geometry,
  sound, video, gun inputs, service mode and authentic gameplay startup;
  **not yet met**.
- **Gate C**: complete faithful start-to-finish HOTD1, all four chapters,
  branches, audio/video, two-player inputs, clean native build and independent
  cabinet-reference validation; **not yet met**.

The data validator forbids **100% overall** unless Gate C is explicitly
marked complete with evidence and earlier gates, and the major areas are
likewise fully completed. Editing gate status is intentionally not an
automatic command: it requires manual review against every criterion and
independent proof. A successful original-ROM synthetic-state instruction
probe is not a continuous boot; a status fixture is not observed hardware;
a visually similar game is not a faithful original native recompilation.

**Always report both**: the individual task's current estimated percentage
and the overall original HOTD1 percentage, with a brief explanation of
what was and was not verified. Avoid promotional "X% of Sega Model 2C is done"
claims that conflate tools, research, and operational hardware.
