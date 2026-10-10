# EPF8282 candidate: feedback relations and validation limits

Date: 2026-10-10. Baseline main: `f24502aa5579d5b153271ea200de3d0a9437a57a`.

**Model 2C is NOT complete. This pass changes research tools only. It does
not supply a new FPGA design, decode routing switches, or alter HOTD1's
CPU, memory bus, serial responses or hardware timing.**

## Question addressed

The candidate's eight LUTs match the compiler's fitted functions and
ordered input slots. Can their interconnected Boolean behavior also be
checked without silently choosing an evaluation order or inventing a
register's initial state?

The new `flex8000_feedback_audit.py` uses the SAME three pinned non-Sega
`testmux` compiler files as the preceding pass. Configuration coordinates,
address XOR 15, output XOR 0 and slot order [0,1,2,3] remain fixed. The
connections are supplied by FIT metadata, **not recovered from the
configuration's routing bits**. Each candidate assignment is checked both
by direct evaluation of the report equations and by lookup into the fixed
candidate tables extracted from the SOF.

Register outputs are independent boundary variables. Register data LUTs
are still checked exactly, but clocks, clear/preset, delays and register
updates are deliberately not modeled. A Boolean fixed point is an
assignment satisfying the combinational equations under those cuts; it is
not necessarily a physically reachable state after reset.

## Measured reference result

The pinned-reference workflow executed the audit against the actual
archived files and returned these counts:

| Quantity | Result |
| --- | ---: |
| Cells | 8: seven combinational, one registered |
| External input variables | 3 |
| Input/held-register boundary cases | 16 |
| Complete assignments examined | 2,048 |
| Truth-table bits matching exactly | 128 / 128 |
| Boundary cases with different candidate/reference solution sets | 0 |
| Total Boolean fixed points across all boundaries | 20 |
| Nontrivial combinational feedback component | Four cells |

The solution-count histogram is **13 boundary cases with one solution,
two with two solutions, and one with three solutions**. Every solution is
preserved. The auditor does not choose the first solution, seed the loop
with zero, or turn a mathematical ambiguity into a claimed hardware state.
The candidate and report match complete sets, not merely the number of
solutions. Dependency analysis tests actual Boolean influence; syntactic
feedback that cancels (for example `a OR NOT a`) is not labeled a functional
cycle.

This result follows from and cross-checks the existing exact cell mapping
plus fitter-supplied wiring. It is **not independent evidence that the
bit layout generalizes to a second design**, nor a decoded HOTD1 netlist.
Its new value is an executable model of the reference's feedback and a
measurement of what this restricted validation can miss.

## A concrete limitation: 82 mutations are invisible to this restricted check

The tool separately changes each one of the 128 candidate truth-table
entries, without refitting any coordinates, polarity or connection:

- Exact cell-table comparison detects **all 128** changes.
- The register-cut fixed-point relation changes for **46** of them.
- **82** changes leave that restricted relation unchanged.

That is not permission to ignore those bits. Unused slot combinations and
the registered cell's data function are examples of behavior not exposed
by this particular relation. Clocked transitions, transient propagation,
initialization and other designs require separate evidence. This shows
why a passing network-level check cannot replace exact cell checks or
sequential validation. Conversely, multiple mathematical solutions do
not establish how an actual device selects a state, its timing, or whether
all cut-register combinations are reachable with asynchronous controls.

## Source identity and execution evidence

Pinned public archive:
`fayaw/spearlegacyLLRF`, commit
`6a0d68153d731518f07e98762f82d25e042838a8`, directory
`spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid`.

- SOF blob: `4bd945df501d848d9fc4fd512945336ec7c24fca`.
- Report blob: `88deb079d565b038b1bc4a71e015fd324dddd3ab`.
- Fitter blob: `12bd9dc6ce31fb3c70bbedb1a6ce9322a40cb10e`.

[The compiler's fitted equations](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.rpt,v)
and [ordered connections](https://github.com/fayaw/spearlegacyLLRF/blob/6a0d68153d731518f07e98762f82d25e042838a8/spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/testmux.fit,v)
are reference inputs, not source code transplanted into ArcadeRecomp.

The initial measurement ran at `ae30e788fd611b23461ef78b26e8a40db9fe9ac7`
in [Actions run 38041270659](https://github.com/Zippingrocks/Arcade-Recomp/actions/runs/38041270659).
The downloaded artifact's SHA-256 was independently checked against
`b9d1778937fc6a691c117b307b059d4a9510c4059a020f24f338e0a95ad79fef`, and its
source-commit record matched. The workflow retains counts and conventions
only: no reference configuration bytes, equations, net names or full
solution states are exported. Observed counts are now regression guards;
CI must not refit the candidate to rescue a failure.

The archival `buff_with_clk` report AND fitter file were checked again;
both explicitly target **EPM5130QC**, not the EPF8282 target of its sibling
SOF. Their archived initial-revision records did not provide a second
compatible build. They remain disqualified for this circuit check.

## Validation

The baseline source ZIP matched CI digest
`3596dcce27905bf5a585248902257a8fb31a5ab733b34cce69ae94684f238aee`.
The baseline full local suite passed **239 tests**. Fourteen new tests
cover feed-forward networks, bistable and inconsistent Boolean loops,
register cuts, fitted inversion aliases, bounded parsing and provenance,
mutation blind spots, and canceled dependencies. They use artificial
networks and independent Boolean/tuple oracles, not archived design data.

The combined source is tested locally and in full-suite CI before main
promotion. Full-suite counts and final code identity are recorded in the
commit/test results rather than extrapolated from earlier reports.

## Original HOTD1 regression actually rerun

The original uploaded archive again passed all **29 chip fingerprints**.
The reconstructed CPU SHA-256 is unchanged:
`da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75`.
A newly compiled strict probe produced:

| Mode | Successful native instructions | Deliberate stop |
| --- | ---: | --- |
| Default strict | 1,904 | IP `0xA375C`, disabled serial TX |
| Documented TX only | 1,910 | IP `0xA372C`, unavailable status at `0x01C0001A` |

Both returned expected diagnostic exit 3. TX2 `FF` and TX1 `01` were
recorded. Neither run used synthetic receive/status data. No new game
runtime source changed and no unsupported hardware access was bypassed.

## Reproduction and remaining gates

```sh
python -m unittest discover -s tests -v
# Explicitly downloads three pinned NON-SEGA compiler files:
python -m arcaderecomp.flex8000_feedback_audit --fetch-reference --output build/research/feedback.json
```

This is not a cycle simulator or a complete FPGA decoder. Actual routing
configuration bits, clock/reset/register behavior, real gun-board replies,
authentic serial timing and the `0x00F80000` board device remain unresolved.
Issues #4/#6 and the [Model 2C completion gates](MODEL2C_DEFINITION_OF_DONE.md)
remain open.
