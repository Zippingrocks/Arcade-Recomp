"""Conservative ahead-of-time C++ emission for selected Intel i960 instructions.

This is a research translator, not a functional Model 2C game runtime.
The generated C++ compiles fixed, decoded instruction semantics. It does not
decode 32-bit i960 instructions during native execution. Unsupported cases
become deliberate stop sites, never silently translated as NOPs.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i960 import Instruction, decode, discover


@dataclass(frozen=True)
class TranslationReport:
    entry: int
    discovered: int
    translated: int
    unsupported: tuple[int, ...]
    limit_reached: bool


def _operand(raw: int, literal: bool) -> str:
    return f"{raw}u" if literal else f"cpu.r[{raw}]"


def _addr(ins: Instruction, word: int, image: bytes) -> str:
    base = (word >> 14) & 31
    if not word & 0x1000:  # MEMA
        offset = word & 0xfff
        return f"(cpu.r[{base}] + {offset}u)" if word & 0x2000 else f"{offset}u"
    mode = (word >> 10) & 15
    scale = (word >> 7) & 7
    index = word & 31
    disp = int.from_bytes(image[ins.pc + 4:ins.pc + 8], "little") if ins.size == 8 else 0
    idx = f"(cpu.r[{index}] << {scale})"
    if mode == 4:
        return f"cpu.r[{base}]"
    if mode == 5:
        return f"({ins.pc + 8}u + {disp}u)"
    if mode == 7:
        return f"(cpu.r[{base}] + {idx})"
    if mode == 12:
        return f"{disp}u"
    if mode == 13:
        return f"(cpu.r[{base}] + {disp}u)"
    if mode == 14:
        return f"({idx} + {disp}u)"
    if mode == 15:
        return f"(cpu.r[{base}] + {idx} + {disp}u)"
    raise ValueError("Unsupported memory address mode")


def _emit_op(ins: Instruction, image: bytes) -> str | None:
    """Return generated C++ statement or None for unsupported semantics."""
    if ins.issue:
        return None
    op = ins.mnemonic
    word = ins.word
    target = f"0x{ins.target:08x}u" if ins.target is not None else None
    if ins.form in ("MEMA", "MEMB") and op == "callx":
        return f"return frame_call(cpu, bus, {_addr(ins, word, image)}, 0x{ins.next_pc:08x}u);"

    if ins.form in ("MEMA", "MEMB") and op in (
        "lda", "ld", "st", "ldob", "ldib", "ldos", "ldis", "stob", "stos"
    ):
        address = _addr(ins, word, image)
        dest = (word >> 19) & 31
        if op == "lda":
            return f"cpu.r[{dest}] = {address};"
        if op == "ld":
            return (f"if (!bus.read32) return stop(cpu, StopCode::missing_bus); "
                    f"cpu.r[{dest}] = bus.read32(bus.ctx, {address});")
        if op == "st":
            return (f"if (!bus.write32) return stop(cpu, StopCode::missing_bus); "
                    f"bus.write32(bus.ctx, {address}, cpu.r[{dest}]);")
        if op in ("ldob", "ldib", "ldos", "ldis"):
            width = 8 if op.endswith("b") else 16
            suffix = "8" if width == 8 else "16"
            check = "0x80u" if width == 8 else "0x8000u"
            fill = "0xffffff00u" if width == 8 else "0xffff0000u"
            expression = ("value" if op.startswith("ldo") else
                          f"((value & {check}) ? (value | {fill}) : value)")
            return (f"if (!bus.read{suffix}) return stop(cpu, StopCode::missing_bus); "
                    f"{{ const std::uint32_t value = bus.read{suffix}(bus.ctx, {address}); "
                    f"cpu.r[{dest}] = {expression}; }}")
        if op in ("stob", "stos"):
            suffix = "8" if op.endswith("b") else "16"
            return (f"if (!bus.write{suffix}) return stop(cpu, StopCode::missing_bus); "
                    f"bus.write{suffix}(bus.ctx, {address}, "
                    f"static_cast<std::uint{suffix}_t>(cpu.r[{dest}]));")

    if ins.form == "REG" and op == "synmovq":
        # Both operands are register pointers: src1 is destination, src2 source.
        # Literal / special encodings are unsupported for this K-series opcode.
        if word & (0x20 | 0x40 | 0x800 | 0x1000):
            return None
        dest_register = word & 31
        src_register = (word >> 14) & 31
        return (f"return sync_move_quad(cpu, bus, cpu.r[{dest_register}], "
                f"cpu.r[{src_register}]);")

    if ins.form == "REG":
        # Special function registers and the full i960 local-register frame
        # model have not been implemented in this tranche.
        if word & (0x20 | 0x40):
            return None
        # The destination-mode field is irrelevant for compare-only REG
        # instructions. Some legitimate ROM instructions set it.
        if word & 0x2000 and op not in ("cmpo", "cmpi"):
            return None
        a = _operand(word & 31, bool(word & 0x800))
        b = _operand((word >> 14) & 31, bool(word & 0x1000))
        dst = (word >> 19) & 31
        if op in ("setbit", "clrbit", "notbit"):
            # Intel documented bit-position modulo 32. All uint32 shifts
            # are masked to avoid host-C++ undefined behavior.
            mask = f"(1u << ({a} & 31u))"
            expr = {"setbit": f"({b} | {mask})",
                    "clrbit": f"({b} & ~{mask})",
                    "notbit": f"({b} ^ {mask})"}[op]
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({expr});"
        if op in ("cmpdeci", "cmpdeco"):
            # Compare src1 with ORIGINAL src2, then decrement src2
            # into dst. Temporaries preserve src1/src2 when registers alias.
            ordered_a = "(lhs ^ 0x80000000u)" if op == "cmpdeci" else "lhs"
            ordered_b = "(rhs ^ 0x80000000u)" if op == "cmpdeci" else "rhs"
            return (f"{{ const std::uint32_t lhs = {a}; "
                    f"const std::uint32_t rhs = {b}; "
                    f"cpu.cc = ({ordered_a} < {ordered_b}) ? 4 : "
                    f"({ordered_a} > {ordered_b}) ? 1 : 2; "
                    f"cpu.r[{dst}] = rhs - 1u; cpu.cc_defined = true; }}")
        if op in ("and", "or", "xor"):
            symbol = {"and": "&", "or": "|", "xor": "^"}[op]
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({b} {symbol} {a});"
        if op in ("addo", "subo"):
            symbol = "+" if op == "addo" else "-"
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({b} {symbol} {a});"
        if op == "mov":
            return f"cpu.r[{dst}] = {a};"
        if op in ("shlo", "shro"):
            symbol = "<<" if op == "shlo" else ">>"
            return f"cpu.r[{dst}] = static_cast<std::uint32_t>({b} {symbol} ({a} & 31u));"
        if op in ("cmpo", "cmpi"):
            # Intel i960 AC.cc[2:0]: L=0b100, E=0b010, G=0b001,
            # measured as src1 compared with src2, NOT src2 vs src1.
            # Signed ordering via XOR 0x80000000 works without relying on
            # implementation-defined uint32-to-int32 conversions.
            left = f"({a} ^ 0x80000000u)" if op == "cmpi" else a
            right = f"({b} ^ 0x80000000u)" if op == "cmpi" else b
            return (f"cpu.cc = ({left} < {right}) ? 4 : ({left} > {right}) ? 1 : 2; "
                    "cpu.cc_defined = true;")
        return None

    if ins.form == "COBR" and (op.startswith("cmpib") or op.startswith("cmpob")):
        # For Intel KB compare-and-branch: src1 compared with src2.
        # A single operand literal is allowed; special-function src2 isn't
        # currently implemented and must fail closed.
        if word & 1:
            return None
        a = _operand((word >> 19) & 31, bool(word & 0x2000))
        b = f"cpu.r[{(word >> 14) & 31}]"
        is_signed = op.startswith("cmpib")
        left = f"({a} ^ 0x80000000u)" if is_signed else a
        right = f"({b} ^ 0x80000000u)" if is_signed else b
        test = op[5:]  # cmpibge -> ge; cmpobne -> ne
        masks = {"g": 1, "e": 2, "ge": 3, "l": 4,
                 "ne": 5, "le": 6, "o": 7, "no": 0}
        if test not in masks:
            return None
        mask = masks[test]
        taken = f"cpu.cc == 0" if mask == 0 else f"(cpu.cc & {mask}) != 0"
        return (f"cpu.cc = ({left} < {right}) ? 4 : ({left} > {right}) ? 1 : 2; "
                f"cpu.cc_defined = true; "
                f"if ({taken}) {{ cpu.ip = {target}; return true; }}")

    if ins.form == "CTRL":
        if op == "call":
            return f"return frame_call(cpu, bus, {target}, 0x{ins.next_pc:08x}u);"
        if op == "ret":
            return "return frame_return(cpu, bus);"
        if op == "b":
            return f"cpu.ip = {target}; return true;"
        masks = {"bg": 1, "be": 2, "bge": 3, "bl": 4,
                 "bne": 5, "ble": 6, "bo": 7, "bno": 0}
        if op in masks:
            mask = masks[op]
            condition = "cpu.cc == 0" if mask == 0 else f"(cpu.cc & {mask}) != 0"
            return (f"if (!cpu.cc_defined) return stop(cpu, StopCode::undefined_condition_code); "
                    f"if ({condition}) {{ cpu.ip = {target}; return true; }}")
        return None

    return None


def emit_cpp(image: bytes, entry: int, max_instructions: int = 256,
             additional_entries: tuple[int, ...] = ()) -> tuple[str, TranslationReport]:
    """Translate reachable, ROM-resident instructions into a native C++ stepper.

    Memory is supplied through explicit device/bus callbacks. Local CALL,
    CALLX and RET are modeled with four cached register frames. Supervisor/fault
    returns, interrupt frames, exact cycles and unimplemented opcodes stop safely. The generated source is game-derived; keep it out of Git.
    """
    graph = discover(image, entry, limit=max_instructions,
                     additional_entries=additional_entries)
    translated = 0
    unsupported = []
    bodies = []
    for pc, ins in sorted(graph["instructions"].items()):
        body = _emit_op(ins, image)
        if body is None:
            unsupported.append(pc)
            body = "return stop(cpu);"
        else:
            translated += 1
            if body.startswith(("return frame_", "return sync_move_quad(")):
                pass  # CALL/RET helper sets the next IP itself
            elif body.startswith("if (") and "return true;" in body and body.endswith("}"):
                body += f" cpu.ip = 0x{ins.next_pc:08x}u; return true;"
            elif not (body.endswith("return true;") or body.endswith("return stop(cpu);")):
                body += f" cpu.ip = 0x{ins.next_pc:08x}u; return true;"
        bodies.append(f"      case 0x{pc:08x}u: {{ {body} }}")
    result = """// GENERATED — private ROM-derived translation output; do not redistribute.
// Original source and opcode bytes are NOT embedded. Only translated operations.
#include <cstdint>
#include "i960_frame_runtime.hpp"
#include "i960_sync_runtime.hpp"

namespace arcaderecomp_generated {
static inline bool step(CPU& cpu, const Bus& bus) {
    switch (cpu.ip) {
""" + "\n".join(bodies) + """
      default: return stop(cpu);
    }
}
} // namespace arcaderecomp_generated
"""
    report = TranslationReport(entry, len(graph["instructions"]), translated,
                               tuple(unsupported), graph["limit_reached"])
    return result, report
