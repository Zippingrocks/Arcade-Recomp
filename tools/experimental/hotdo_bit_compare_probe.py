"""Check selected original HOTD instruction sites with synthetic CPU state.

Requires a private, hash-verified original CPU image plus the repository's
synthetic oracle module. Generated game code is confined to a temporary
folder; only counts, addresses and hashes are written to the report.
This is not a continuous boot, a hardware oracle, or a game completion test.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from arcaderecomp.i960_cpp import emit_cpp
from test_i960_bit_compare_native import Fixture, MASK, NATIVE_RUNNER, VALUES, vector_line

EXPECTED_SHA256 = "da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75"
# Sites selected from the baseline two-root graph; no instruction bytes stored.
SITES = {
    0x13904: "test", 0x13ad4: "chkbit", 0x1565c: "bbc",
    0x158c0: "not", 0x158cc: "not", 0x158d4: "not",
    0x15940: "andnot", 0x15a38: "andnot", 0x16bd0: "bbc",
    0x16c38: "bbc", 0x1a9b8: "chkbit", 0x1e9ec: "bbc",
    0x33b50: "bbc", 0xa1bf4: "cmpinco", 0xa1c48: "cmpinco",
    0xa36cc: "cmpinco", 0xa3700: "bbs",
}


def verify(image: bytes, compilers: list[str]) -> dict:
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != 2**21 or digest != EXPECTED_SHA256:
        raise ValueError("expected the authenticated original hotdo 2 MiB CPU image")
    if not compilers:
        raise ValueError("at least one explicitly selected compiler is required")
    resolved = []
    for compiler in compilers:
        path = shutil.which(compiler)
        if not path:
            raise ValueError(f"requested C++ compiler is unavailable: {compiler}")
        resolved.append(path)
    source, coverage = emit_cpp(image, 0x5f0, 16384, (0x6b0,))
    if set(SITES).intersection(coverage.unsupported) or coverage.limit_reached:
        raise ValueError("selected original sites are not fully translated")
    vectors = []
    site_counts = {}
    rng = random.Random(0x960b17)
    for pc, op in SITES.items():
        word = struct.unpack_from("<I", image, pc)[0]
        dst = (word >> 19) & 31
        if op == "test":
            fixture = Fixture("original", op, dst=dst, test_mask=(word >> 24) - 0x20,
                              literal_a=bool(word & 0x2000))
        elif op in ("bbc", "bbs"):
            displacement = word & 0x1ffc
            if displacement >= 0x1000:
                displacement -= 0x2000
            fixture = Fixture("original", op, dst, (word >> 14) & 31,
                              literal_a=bool(word & 0x2000), displacement=displacement,
                              extra_bits=word & 2)
        else:
            fixture = Fixture("original", op, word & 31, (word >> 14) & 31, dst,
                              bool(word & 0x800), bool(word & 0x1000),
                              extra_bits=word & 0x2000)
        if fixture.word() != word:
            raise ValueError(f"unexpected original encoding at 0x{pc:08x}")
        if op == "test":
            samples = [(0, 0, cc, defined) for cc in range(8) for defined in (False, True)]
        else:
            samples = [(a, b, (ai + bi) % 8, bool((ai + bi) % 2))
                       for ai, a in enumerate(VALUES) for bi, b in enumerate(VALUES)]
            samples += [(rng.getrandbits(32), rng.getrandbits(32), rng.randrange(8),
                         bool(rng.randrange(2))) for _ in range(12)]
        for a, b, cc, defined in samples:
            registers = [((r + 7) * 0x103070a1) & MASK for r in range(32)]
            if not fixture.literal_a:
                registers[fixture.a] = a
            if not fixture.literal_b:
                registers[fixture.b] = b
            vectors.append(vector_line(fixture, pc, registers, cc, defined))
        site_counts[f"0x{pc:08x}"] = len(samples)
    compiler_results = []
    with tempfile.TemporaryDirectory(prefix="private-hotdo-bit-check-") as temp:
        folder = Path(temp)
        cpp = folder / "private_generated.cpp"
        cpp.write_text(source + NATIVE_RUNNER, encoding="utf-8")
        for index, compiler in enumerate(resolved):
            binary = folder / f"native-{index}"
            flags = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-fsanitize=undefined",
                     "-fno-sanitize-recover=all"]
            subprocess.run([compiler, *flags, "-I", str(ROOT / "runtime"),
                            str(cpp), "-o", str(binary)], check=True,
                           text=True, capture_output=True, timeout=120)
            run = subprocess.run([str(binary)], input="".join(vectors), check=True,
                                 text=True, capture_output=True, timeout=30)
            if run.stderr or int(run.stdout) != len(vectors):
                raise ValueError("native checker did not validate every supplied case")
            version = subprocess.run([compiler, "--version"], check=True, text=True,
                                     capture_output=True, timeout=10).stdout.splitlines()[0]
            compiler_results.append({"version": version, "flags": flags,
                                     "passed_vectors": len(vectors), "stderr_empty": True})
    return {
        "schema": "hotdo-bit-compare-isolated-v1", "image_sha256": digest,
        "synthetic_cpu_state": True, "continuous_boot": False,
        "hardware_verified": False, "rom_data_exported": False,
        "original_site_count": len(SITES), "vectors_per_site": site_counts,
        "instruction_families": dict(Counter(SITES.values())),
        "graph": {"candidates": coverage.discovered, "translated": coverage.translated,
                  "unsupported": [f"0x{pc:08x}" for pc in coverage.unsupported],
                  "limit_reached": coverage.limit_reached},
        "compilers": compiler_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", action="append", help="repeat for each compiler; default GCC and Clang")
    args = parser.parse_args()
    try:
        if args.output.resolve() == args.image.resolve():
            raise ValueError("the report must not overwrite the input image")
        report = verify(args.image.read_bytes(), args.cxx or ["g++", "clang++"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never print generated source or compiler diagnostics containing game code.
        print(f"verification failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"Verified {len(SITES)} original instruction sites with synthetic CPU state only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
