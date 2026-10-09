"""Independent synthetic oracles for Intel KB bit/condition/compare lowering.

No Sega instructions or game data. The Python oracle uses named fixture
semantics, never the decoder or emitted C++, to construct expected CPU state.
Every native group is executed with each installed GCC/Clang compiler and UBSan.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
MASK = (1 << 32) - 1
VALUES = (0, 1, 2, 31, 32, 63, 0x7fffffff, 0x80000000,
          0x80000001, 0xfffffffe, 0xffffffff, 0x55555555, 0xaaaaaaaa)
OPCODES = {"not": 0x58a, "andnot": 0x582, "chkbit": 0x5ae,
           "cmpinco": 0x5a4, "cmpinci": 0x5a5,
           "cmpdeco": 0x5a6, "cmpdeci": 0x5a7}


def reg_word(op: str, a: int, b: int, dst: int,
             literal_a: bool = False, literal_b: bool = False) -> int:
    code = OPCODES[op]
    return ((code >> 4) << 24 | dst << 19 | b << 14 |
            int(literal_a) << 11 | int(literal_b) << 12 |
            (code & 15) << 7 | a)


def signed32(value: int) -> int:
    return value if value < 2**31 else value - 2**32


@dataclass(frozen=True)
class Fixture:
    group: str
    op: str
    a: int = 4
    b: int = 5
    dst: int = 6
    literal_a: bool = False
    literal_b: bool = False
    displacement: int = 12
    test_mask: int = 0
    extra_bits: int = 0
    reject: bool = False

    def word(self) -> int:
        if self.op == "test":
            value = (0x20 + self.test_mask) << 24 | self.dst << 19
            value |= int(self.literal_a) << 13
        elif self.op in ("bbc", "bbs"):
            value = (0x30 if self.op == "bbc" else 0x37) << 24
            value |= self.a << 19 | self.b << 14
            value |= int(self.literal_a) << 13 | self.displacement & 0x1ffc
        else:
            value = reg_word(self.op, self.a, self.b, self.dst,
                             self.literal_a, self.literal_b)
        return value | self.extra_bits

    def expected(self, pc: int, registers: list[int], cc: int,
                 defined: bool) -> tuple[list[int], int, int, bool, bool, int, int]:
        # This is an independent model of the manual's functional semantics.
        out = list(registers)
        if self.reject:
            return out, pc, cc, defined, False, 1, pc
        if self.op == "test":
            if not defined:
                return out, pc, cc, defined, False, 16, pc
            # Spell out the truth sets, rather than sharing emitter bit masks.
            truth = ({0}, {1, 3, 5, 7}, {2, 3, 6, 7}, {1, 2, 3, 5, 6, 7},
                     {4, 5, 6, 7}, {1, 3, 4, 5, 6, 7},
                     {2, 3, 4, 5, 6, 7}, {1, 2, 3, 4, 5, 6, 7})
            out[self.dst] = int(cc in truth[self.test_mask])
            return out, pc + 4, cc, defined, True, 0, 0
        a = self.a if self.literal_a else registers[self.a]
        b = self.b if self.literal_b else registers[self.b]
        next_pc = pc + 4
        if self.op == "not":
            out[self.dst] = MASK - a
        elif self.op == "andnot":
            # Per-bit truth table keeps operand ordering independently visible.
            out[self.dst] = sum(2**bit for bit in range(32)
                                 if (b // 2**bit) % 2 and not (a // 2**bit) % 2)
        elif self.op in ("chkbit", "bbc", "bbs"):
            selected = (b // 2**(a % 32)) % 2
            cc, defined = 2 * selected, True
            if self.op in ("bbc", "bbs"):
                take = selected == (1 if self.op == "bbs" else 0)
                if take:
                    next_pc = (pc + self.displacement) % 2**32
        elif self.op.startswith("cmp"):
            left, right = (signed32(a), signed32(b)) if self.op.endswith("i") else (a, b)
            cc = 4 if left < right else 1 if left > right else 2
            delta = 1 if self.op.startswith("cmpinc") else -1
            out[self.dst] = (b + delta) % 2**32
            defined = True
        else:
            raise ValueError(self.op)
        return out, next_pc, cc, defined, True, 0, 0


def fixtures() -> list[Fixture]:
    result: list[Fixture] = []
    aliases = ((4, 5, 6), (4, 5, 4), (4, 5, 5), (4, 4, 4), (31, 20, 31))
    for op in ("not", "andnot", "cmpinco", "cmpinci", "cmpdeco", "cmpdeci"):
        group = "decrement_regression" if op.startswith("cmpdec") else op
        for a, b, dst in aliases:
            for modes in range(4):
                result.append(Fixture(group, op, a, b, dst,
                                      bool(modes & 1), bool(modes & 2)))
        # Literal extremes in either input, including both literal operands.
        for value in (0, 1, 31):
            result.append(Fixture(group, op, value, 5, 6, True))
            result.append(Fixture(group, op, 4, value, 6, False, True))
            result.append(Fixture(group, op, value, value, 6, True, True))
    for modes in range(4):
        for a, b, _ in aliases:
            result.append(Fixture("chkbit", "chkbit", a, b,
                                  literal_a=bool(modes & 1), literal_b=bool(modes & 2)))
    for a in (0, 1, 31):
        result.append(Fixture("chkbit", "chkbit", a, literal_a=True))
    result.append(Fixture("ignored_chkbit_destination", "chkbit", dst=31, extra_bits=0x2000))
    for op in ("bbc", "bbs"):
        for literal in (False, True):
            for displacement in (-8, 0, 12):
                for prediction in (0, 2):
                    for a, b in ((4, 5), (4, 4), (31, 20)):
                        result.append(Fixture("branches", op, a, b, literal_a=literal,
                                              displacement=displacement, extra_bits=prediction))
        for a in (0, 1, 31):
            result.append(Fixture("branches", op, a, literal_a=True))
    for mask in range(8):
        for dst in (0, 4, 20, 31):
            for m1 in (False, True):
                result.append(Fixture("test_conditions", "test", dst=dst,
                                      test_mask=mask, literal_a=m1))
    for op in OPCODES:
        for flag in (0x20, 0x40):
            result.append(Fixture("unsupported_encodings", op, extra_bits=flag, reject=True))
        if op != "chkbit":
            result.append(Fixture("unsupported_encodings", op, extra_bits=0x2000, reject=True))
    for op in ("bbc", "bbs", "test"):
        result.append(Fixture("unsupported_encodings", op, extra_bits=1, reject=True))
    return result


NATIVE_RUNNER = r'''
#include <iostream>
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    std::uint32_t pc, initial_cc, initial_defined, good, next, cc, defined, reason, stop_ip;
    unsigned vector = 0;
    while (std::cin >> pc) {
        if (!(std::cin >> initial_cc >> initial_defined >> good >> next >> cc
                      >> defined >> reason >> stop_ip)) return 90;
        CPU cpu{};
        cpu.ip = pc; cpu.cc = static_cast<int>(initial_cc);
        cpu.cc_defined = initial_defined != 0;
        std::uint32_t expected[32]{};
        for (auto& value : cpu.r) if (!(std::cin >> value)) return 91;
        for (auto& value : expected) if (!(std::cin >> value)) return 92;
        const bool success = step(cpu, bus);
        if (success != (good != 0) || cpu.ip != next || cpu.cc != static_cast<int>(cc)
            || cpu.cc_defined != (defined != 0)
            || static_cast<std::uint32_t>(cpu.stop_code) != reason || cpu.stop_ip != stop_ip) {
            std::cerr << "control mismatch vector=" << vector << " pc=" << pc
                      << " next=" << cpu.ip << " expected=" << next
                      << " cc=" << cpu.cc << " expected=" << cc << '\n';
            return 1;
        }
        for (unsigned r = 0; r < 32; ++r) if (cpu.r[r] != expected[r]) {
            std::cerr << "register mismatch vector=" << vector << " pc=" << pc
                      << " r=" << r << " actual=" << cpu.r[r]
                      << " expected=" << expected[r] << '\n';
            return 2;
        }
        ++vector;
    }
    if (!std::cin.eof() || vector == 0) return 93;
    std::cout << vector << '\n';
}
'''


def vector_line(fixture: Fixture, pc: int, registers: list[int],
                cc: int, defined: bool) -> str:
    regs, nxt, newcc, newdef, ok, reason, stop_ip = fixture.expected(pc, registers, cc, defined)
    numbers = (pc, cc, int(defined), int(ok), nxt, newcc, int(newdef), reason, stop_ip,
               *registers, *regs)
    return " ".join(str(n) for n in numbers) + "\n"


class I960BitCompareNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = [shutil.which(name) for name in ("g++", "clang++")]
        compilers = [c for c in compilers if c]
        if not compilers:
            raise unittest.SkipTest("GCC/Clang C++ compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        folder = Path(cls.folder.name)
        choices = fixtures()
        image = bytearray(b"\xff" * (32 * len(choices) + 32))
        entries = []
        cls.groups: dict[str, list[str]] = {}
        rng = random.Random(0x960)
        for index, fixture in enumerate(choices):
            pc = index * 32 + 8
            entries.append(pc)
            struct.pack_into("<I", image, pc, fixture.word())
            group = cls.groups.setdefault(fixture.group, [])
            if fixture.op == "test":
                samples = [(0, 0, cc, defined) for cc in range(8) for defined in (False, True)]
            else:
                samples = [(a, b, (ai + bi) % 8, bool((ai + bi) % 2))
                           for ai, a in enumerate(VALUES) for bi, b in enumerate(VALUES)]
                samples += [(rng.getrandbits(32), rng.getrandbits(32), rng.randrange(8),
                             bool(rng.randrange(2))) for _ in range(12)]
            for a, b, cc, defined in samples:
                regs = [((r + 3) * 0x10204081) & MASK for r in range(32)]
                if not fixture.literal_a:
                    regs[fixture.a] = a
                if not fixture.literal_b:
                    regs[fixture.b] = b
                group.append(vector_line(fixture, pc, regs, cc, defined))
        source, report = emit_cpp(bytes(image), entries[0], len(image), tuple(entries[1:]))
        expected_translated = sum(not f.reject for f in choices)
        if report.translated != expected_translated or report.limit_reached:
            raise AssertionError((report, expected_translated))
        cpp = folder / "synthetic.cpp"
        cpp.write_text(source + NATIVE_RUNNER, encoding="utf-8")
        cls.binaries = []
        for index, compiler in enumerate(compilers):
            binary = folder / f"native-{index}"
            built = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                    "-I", str(RUNTIME), str(cpp), "-o", str(binary)],
                                   text=True, capture_output=True, timeout=60)
            if built.returncode:
                raise AssertionError(f"{compiler}: {built.stderr}")
            cls.binaries.append((compiler, binary))

    def check_group(self, name: str):
        vectors = self.groups[name]
        for compiler, binary in self.binaries:
            with self.subTest(compiler=compiler, group=name, cases=len(vectors)):
                run = subprocess.run([str(binary)], input="".join(vectors), text=True,
                                     capture_output=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stderr, "", run.stderr)
                self.assertEqual(int(run.stdout), len(vectors))

    def test_not_operand_modes_and_aliases(self):
        self.check_group("not")

    def test_andnot_operand_order_modes_and_aliases(self):
        self.check_group("andnot")

    def test_cmpinco_compare_before_increment_and_wrap(self):
        self.check_group("cmpinco")

    def test_cmpinci_signed_order_and_ignored_overflow(self):
        self.check_group("cmpinci")

    def test_existing_decrement_semantics_do_not_regress(self):
        self.check_group("decrement_regression")

    def test_chkbit_modulo_positions_and_cc_replacement(self):
        self.check_group("chkbit")

    def test_chkbit_destination_field_is_ignored(self):
        self.check_group("ignored_chkbit_destination")

    def test_bit_branches_paths_prediction_aliases_and_cc(self):
        self.check_group("branches")

    def test_testcc_truth_table_undefined_guard_and_ignored_m1(self):
        self.check_group("test_conditions")

    def test_unsupported_special_encodings_fail_closed(self):
        self.check_group("unsupported_encodings")


if __name__ == "__main__":
    unittest.main()
