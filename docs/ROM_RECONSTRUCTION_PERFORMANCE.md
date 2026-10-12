# Faster ROM reconstruction, unchanged bytes

Date: 2026-10-11. This measures **host ROM reconstruction only**, not native
game execution, Model 2C timing, gameplay FPS or hardware fidelity.

`arcaderecomp/roms.py` now uses native byte searches for its private 0/1
occupancy bitmap. Contiguous chips copy as one block instead of splitting
and recombining lanes. Interleaved chips retain the same wiring; mirrors
still require every source byte loaded and every destination byte unused.
Negative offsets, empty loads, negative mirror endpoints and nonpositive
mirror lengths are rejected before Python slicing can reinterpret them.
No chip authentication check is removed or weakened.

## Reproduce without game data

```sh
python -m tools.benchmark_rom_reconstruction --chip-kib 4096 --rounds 9
python -m unittest discover -s tests -p 'test_rom*.py' -v
```

The benchmark generates four entirely synthetic layouts and checks output
equality before and after every timed trial. Its reference reproduces the
previous lane/`any`/`all` algorithm at commit
`5ef4bb37ed771592927e432fd273a1eded5a349b` for valid inputs; it is not a ROM
validator. Timed order alternates each trial. Results include environment,
medians and output hashes. There is deliberately no CI speed threshold.

On this Windows host, Python 3.12.10, nine trials with 4 MiB synthetic chips:

| Synthetic layout | Previous median | New median | Speedup |
| --- | ---: | ---: | ---: |
| Two interleaved chips | 42.62 ms | 17.83 ms | 2.39× |
| Contiguous chip | 22.08 ms | 5.07 ms | 4.36× |
| Swapped contiguous chip | 20.56 ms | 6.92 ms | 2.97× |
| Swapped chip plus mirror | 50.01 ms | 12.44 ms | 4.02× |

These are local measurements, not portable performance guarantees. File I/O,
archive decompression and authentication are outside the timed interval.

## Private original-set parity

All 29 original `hotdo` chips were locally matched against manifest size,
CRC32 and SHA-1. Every reconstructed region matched the actual previous
`reconstruct()` implementation byte for byte, including all seven alternating
timed trials. No ROM bytes or reconstructed images are included here.

| Region | Previous median | New median | Speedup |
| --- | ---: | ---: | ---: |
| maincpu | 10.38 ms | 4.14 ms | 2.51× |
| main_data | 192.29 ms | 69.54 ms | 2.77× |
| copro_data | 9.51 ms | 6.45 ms | 1.48× |
| polygons | 183.89 ms | 81.26 ms | 2.26× |
| textures | 86.94 ms | 37.63 ms | 2.31× |
| audiocpu | 2.81 ms | 1.12 ms | 2.50× |
| samples | 42.63 ms | 15.15 ms | 2.81× |

The public tests independently place bytes for all 528 legal group/stride
combinations, with and without byte swapping (1,056 cases), including exact
end boundaries. They also exercise zero-valued occupied lanes, mixed
contiguous/interleaved chips, chained mirrors, unloaded mirror sources,
overlaps and malformed bounds. Sixteen focused tests pass locally.

This is synthetic and authenticated original-byte parity evidence, not an
arcade-reference measurement. Estimated ROM tooling remains 95%, Model 2C
20%, overall original HOTD1 10%; Gates A/B/C remain open.
