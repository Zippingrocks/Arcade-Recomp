"""ROM-free host reconstruction benchmark; not arcade timing or game FPS.

Run from the repository root: python -m tools.benchmark_rom_reconstruction
The reference reproduces reconstruct() at 5ef4bb37 for valid benchmark inputs.
It is a speed baseline, NOT a second implementation for accepting real ROMs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time

from arcaderecomp.roms import reconstruct


def baseline_reconstruct(region, matches):
    """Previous lane/any/all implementation, only for generated valid cases."""
    memory = bytearray(region["size"])
    used = bytearray(region["size"])
    for spec in region["loads"]:
        data = matches[spec["file"]]
        if spec.get("swap16"):
            swapped = bytearray(len(data))
            swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
            data = swapped
        group, stride, offset = spec["group"], spec["stride"], spec["offset"]
        for lane in range(group):
            segment = data[lane::group]
            start = offset + lane
            stop = start + len(segment) * stride
            if any(used[start:stop:stride]):
                raise AssertionError("invalid benchmark overlap")
            memory[start:stop:stride] = segment
            used[start:stop:stride] = b"\x01" * len(segment)
    for mirror in region.get("copies", []):
        src, dst, length = mirror["source"], mirror["target"], mirror["size"]
        if not all(used[src:src + length]) or any(used[dst:dst + length]):
            raise AssertionError("invalid benchmark mirror")
        memory[dst:dst + length] = memory[src:src + length]
        used[dst:dst + length] = b"\x01" * length
    return bytes(memory)


def cases(chip_kib=1024):
    if not 1 <= chip_kib <= 16384:
        raise ValueError("chip_kib must be in 1..16384")
    raw = bytes(range(256)) * (chip_kib * 4)
    size = len(raw)
    matches = {"a": raw, "b": raw[::-1]}
    for name, group, stride, swap, mirror in (
            ("interleaved_pair", 2, 4, False, False),
            ("contiguous", 2, 2, False, False),
            ("swapped_contiguous", 1, 1, True, False),
            ("swapped_mirrored", 1, 1, True, True)):
        region = {"size": size * (2 if mirror or stride != group else 1),
                  "loads": [{"file": "a", "group": group, "stride": stride,
                             "offset": 0, "swap16": swap}]}
        if stride != group:
            region["loads"].append({"file": "b", "group": group,
                                    "stride": stride, "offset": group})
        if mirror:
            region["copies"] = [{"source": 0, "target": size, "size": size}]
        yield name, region, matches


def benchmark(rounds=7, chip_kib=1024):
    if not 1 <= rounds <= 100:
        raise ValueError("rounds must be in 1..100")
    results = []
    for name, region, matches in cases(chip_kib):
        expected = baseline_reconstruct(region, matches)
        if reconstruct(region, matches) != expected:
            raise AssertionError("reconstruction parity failed")
        timings = {"baseline": [], "current": []}
        implementations = (("baseline", baseline_reconstruct), ("current", reconstruct))
        for trial in range(rounds):
            for label, implementation in implementations[::1 if trial % 2 == 0 else -1]:
                start = time.perf_counter()
                actual = implementation(region, matches)
                timings[label].append(time.perf_counter() - start)
                if actual != expected:
                    raise AssertionError("timed reconstruction parity failed")
        old, new = (statistics.median(timings[label]) for label in ("baseline", "current"))
        results.append({"case": name, "region_bytes": len(expected),
                        "sha256": hashlib.sha256(expected).hexdigest(),
                        "baseline_median_ms": old * 1000, "current_median_ms": new * 1000,
                        "speedup": old / new})
    return {"scope": "synthetic host ROM reconstruction only; not gameplay FPS",
            "python": platform.python_version(), "platform": platform.platform(),
            "baseline_commit": "5ef4bb37ed771592927e432fd273a1eded5a349b",
            "rounds": rounds, "chip_kib": chip_kib, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--chip-kib", type=int, default=1024)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100 or not 1 <= args.chip_kib <= 16384:
        parser.error("rounds must be 1..100 and chip-kib must be 1..16384")
    print(json.dumps(benchmark(args.rounds, args.chip_kib), indent=2))


if __name__ == "__main__":
    main()
