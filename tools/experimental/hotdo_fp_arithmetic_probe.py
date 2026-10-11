"""Validate ORIGINAL hotdo MULR/DIVR native AOT sites with synthetic registers.

This is an isolated, authenticated-original-byte CPU instruction test, not
continuous boot, an Intel floating-point fault model, or arcade hardware proof.
Original game bytes and ROM-derived translated C++ are used in a private
TemporaryDirectory only. Only integer-only metadata is written as JSON.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ORIGINAL_SHA = "da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75"
# Original-code LOCATION/REGISTER metadata, not instruction or ROM bytes.
SITES = (
    (0x000011f8, "divr", ("r4", "g4", "g6"), 4, 20, 22),
    (0x00001390, "mulr", ("g5", "g13", "g4"), 21, 29, 20),
    (0x00013d88, "mulr", ("g5", "r7", "g5"), 21, 7, 21),
)
MIN_NORMAL = Fraction(1, 1 << 126)
MAX_NORMAL = Fraction((1 << 24) - 1, 1 << 23) * (1 << 127)


def _float32(raw: int) -> float:
    return struct.unpack("<f", struct.pack("<I", raw))[0]


def oracle(mnemonic: str, a: int, b: int) -> tuple[int, int]:
    """Independent rational IEEE-754 oracle; code is stop reason, then bits.

    0 success, 1 inexact, 2 exceptional format/range, 3 divide-by-zero.
    For DIVR, source 1 (a) is the denominator, source 2 (b) the numerator.
    """
    ae, be = (a >> 23) & 255, (b >> 23) & 255
    af, bf = a & 0x7fffff, b & 0x7fffff
    if ae == 255 or be == 255 or (ae == 0 and af) or (be == 0 and bf):
        return 2, 0
    sign = (a ^ b) & 0x80000000
    if mnemonic == "divr" and ae == 0:
        return 3, 0
    if ae == 0 or be == 0:
        return 0, sign
    va, vb = Fraction.from_float(_float32(a)), Fraction.from_float(_float32(b))
    exact = va * vb if mnemonic == "mulr" else vb / va
    if abs(exact) < MIN_NORMAL or abs(exact) > MAX_NORMAL:
        return 2, 0
    bits = struct.unpack("<I", struct.pack("<f", float(exact)))[0]
    return (0, bits) if Fraction.from_float(_float32(bits)) == exact else (1, 0)


def sample_pairs() -> list[tuple[int, int]]:
    edges = (
        0, 0x80000000, 0x3f800000, 0xbf800000, 0x40000000,
        0xc0000000, 0x40400000, 0x3f000000, 0x00800000,
        0x7f7fffff, 0xff7fffff, 1, 0x007fffff,
        0x7f800000, 0xff800000, 0x7fc00001, 0x3f800001,
    )
    cases = [(a, b) for a in edges for b in edges]
    rng = random.Random(0x960784)
    for _ in range(1100):
        ea, eb = rng.randrange(1, 255), rng.randrange(1, 255)
        cases.append(((rng.getrandbits(1) << 31) | (ea << 23) | rng.getrandbits(23),
                      (rng.getrandbits(1) << 31) | (eb << 23) | rng.getrandbits(23)))
    for _ in range(350):
        ea, eb = rng.randrange(115, 139), rng.randrange(115, 139)
        cases.append(((rng.getrandbits(1) << 31) | (ea << 23) | rng.getrandbits(23),
                      (rng.getrandbits(1) << 31) | (eb << 23) | rng.getrandbits(23)))
    # Powers of two generate many exactly representable cross-sign products/ratios.
    for a in range(1, 255, 17):
        for b in range(1, 255, 13):
            cases.append((a << 23, b << 23))
    return cases


RUNNER = r"""
#include <iostream>
using namespace arcaderecomp_generated;
int main() {
    Bus bus{}; unsigned checked=0;
    unsigned pc=0, src1=0, src2=0, dst=0, a=0, b=0, kind=0, want=0;
    while(std::cin>>pc>>src1>>src2>>dst>>a>>b>>kind>>want){
        CPU cpu{};
        cpu.ip=pc;
        for(unsigned i=0;i<32u;++i) cpu.r[i]=(i+1u)*0x01020304u;
        cpu.r[src1]=a;
        cpu.r[src2]=b;
        cpu.cc=5;cpu.cc_defined=true;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        std::uint32_t saved[32]{};
        for(unsigned i=0;i<32u;++i)saved[i]=cpu.r[i];
        const bool completed=step(cpu,bus);
        if(kind==0u) {
            if(!completed||cpu.ip!=pc+4u||cpu.r[dst]!=want||
               cpu.stop_code!=StopCode::none)return 1;
        }else{
            const StopCode reason=kind==1u?
                StopCode::unsupported_floating_rounding:kind==2u?
                StopCode::unsupported_floating_format:
                StopCode::unsupported_floating_division_fault;
            if(completed||cpu.ip!=pc||cpu.stop_ip!=pc||
               cpu.stop_code!=reason)return 2;
        }
        for(unsigned i=0;i<32u;++i)
            if((kind!=0u||i!=dst)&&cpu.r[i]!=saved[i])return 3;
        if(cpu.cc!=5||!cpu.cc_defined||
           !cpu.integer_overflow_mask||!cpu.integer_overflow_mask_defined||
           !cpu.integer_overflow_flag||!cpu.integer_overflow_flag_defined||
           cpu.pending_integer_overflow.pending)return 4;
        ++checked;
    }
    if(!std::cin.eof()||!checked)return 5;
    std::cout<<checked<<'\n';
    return 0;
}
"""


def verify(image: bytes, compilers: list[str]) -> dict:
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != 0x200000 or digest != ORIGINAL_SHA:
        raise ValueError("not authenticated original hotdo CPU image")
    resolved = [shutil.which(x) for x in compilers]
    if not resolved or not all(resolved):
        raise ValueError("requested native compiler unavailable")
    sparse = bytearray(b"\xff" * (SITES[-1][0] + 8))
    for pc, name, operand_names, src1, src2, dest in SITES:
        inst = decode(image, pc)
        if inst.mnemonic != name or inst.form != "REG" or inst.operands != operand_names:
            raise ValueError("original floating-point instruction/register mismatch")
        sparse[pc:pc + 4] = image[pc:pc + 4]
    generated, report = emit_cpp(bytes(sparse), SITES[0][0], 16,
                                 additional_entries=tuple(x[0] for x in SITES[1:]))
    if (report.translated != len(SITES) or report.limit_reached or
            any(pc in report.unsupported for pc, *_ in SITES)):
        raise ValueError("incomplete native translation of original sites")
    pairs = sample_pairs()
    records = []
    for pc, name, _, src1, src2, dest in SITES:
        for a, b in pairs:
            kind, value = oracle(name, a, b)
            records.append(f"{pc} {src1} {src2} {dest} {a} {b} {kind} {value}\n")
    streamed = "".join(records)
    checked = []
    with tempfile.TemporaryDirectory(prefix="private-original-hotdo-fp-arithmetic-") as d:
        source = Path(d) / "original.cpp"
        source.write_text(generated + RUNNER, encoding="utf-8")
        for i, compiler in enumerate(resolved):
            binary = Path(d) / f"native_{i}"
            built = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=60)
            if built.returncode:
                raise ValueError("private native compilation failed")
            ran = subprocess.run([str(binary)], input=streamed,
                                 capture_output=True, text=True, timeout=50)
            if ran.returncode or ran.stderr or ran.stdout.strip() != str(len(records)):
                raise ValueError("original native arithmetic diverged from independent oracle")
            checked.append({"compiler": Path(compiler).name,
                            "passed_vectors": len(records), "ubsan": True})
    return {"schema": "hotdo-original-native-fp-arithmetic-v1",
            "cpu_sha256": digest,
            "site_addresses": [f"0x{p:08x}" for p, *_ in SITES],
            "samples_per_site": len(pairs),
            "exact_subset_only": True,
            "synthetic_cpu_state": True,
            "continuous_original_boot": False,
            "physical_hardware_verified": False,
            "original_bytes_or_generated_game_code_exported": False,
            "compilers": checked}


def write_metadata(image_path: Path, output: Path, report: dict) -> None:
    if image_path.resolve() == output.resolve() or (
            output.exists() and image_path.samefile(output)):
        raise ValueError("metadata output aliases the original CPU image")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=output.parent, prefix=".hotdo-arithmetic-", suffix=".tmp",
                delete=False) as out:
            temp = Path(out.name)
            out.write(json.dumps(report, indent=2) + "\n")
        os.replace(temp, output)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", action="append")
    args = parser.parse_args()
    try:
        if args.image.resolve() == args.output.resolve() or (
                args.output.exists() and args.image.samefile(args.output)):
            raise ValueError("output aliases original image")
        report = verify(args.image.read_bytes(), args.cxx or ["g++", "clang++"])
        write_metadata(args.image, args.output, report)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("private arithmetic validation failed: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    print("Verified three original CPU arithmetic sites with synthetic state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
