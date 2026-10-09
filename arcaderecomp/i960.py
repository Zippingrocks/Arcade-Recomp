"""Intel i960 instruction decoding and conservative control-flow discovery.

Original ArcadeRecomp code written from Intel's publicly documented formats.
This module does NOT emulate the CPU or execute commercial game code.
Unknown, malformed, or unsupported instruction forms remain explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import struct


class DecodeError(ValueError):
    """Instruction stream is truncated or misaligned."""


def signed(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def reg(index: int) -> str:
    if not 0 <= index < 32:
        raise ValueError("i960 register out of range")
    return ("r" if index < 16 else "g") + str(index % 16)


# Identifiers come from published Intel 80960KB/Jx instruction encodings.
CONTROL = {0x08: "b", 0x09: "call", 0x0a: "ret", 0x0b: "bal",
           0x10: "bno", 0x11: "bg", 0x12: "be", 0x13: "bge",
           0x14: "bl", 0x15: "bne", 0x16: "ble", 0x17: "bo",
           0x18: "faultno", 0x19: "faultg", 0x1a: "faulte",
           0x1b: "faultge", 0x1c: "faultl", 0x1d: "faultne",
           0x1e: "faultle", 0x1f: "faulto"}
COMPARE_BRANCH = {**dict(zip(range(0x20, 0x28),
                             ("testno", "testg", "teste", "testge",
                              "testl", "testne", "testle", "testo"))),
                  **dict(zip(range(0x30, 0x40),
                             ("bbc", "cmpobg", "cmpobe", "cmpobge",
                              "cmpobl", "cmpobne", "cmpoble", "bbs",
                              "cmpibno", "cmpibg", "cmpibe", "cmpibge",
                              "cmpibl", "cmpibne", "cmpible", "cmpibo")))}
# REG mnemonic -> operand form. "sss"=source1,source2,destination;
# "ss"=two sources; "sd"=one source, one destination.
REGISTER = {
    0x580: ("notbit", "sss"), 0x581: ("and", "sss"),
    0x582: ("andnot", "sss"), 0x583: ("setbit", "sss"),
    0x584: ("notand", "sss"), 0x586: ("xor", "sss"),
    0x587: ("or", "sss"), 0x588: ("nor", "sss"),
    0x589: ("xnor", "sss"), 0x58a: ("not", "sd"),
    0x58b: ("ornot", "sss"), 0x58c: ("clrbit", "sss"),
    0x58d: ("notor", "sss"), 0x58e: ("nand", "sss"),
    0x58f: ("alterbit", "sss"),
    0x590: ("addo", "sss"), 0x591: ("addi", "sss"),
    0x592: ("subo", "sss"), 0x593: ("subi", "sss"),
    0x594: ("cmpob", "ss"), 0x595: ("cmpib", "ss"),
    0x596: ("cmpos", "ss"), 0x597: ("cmpis", "ss"),
    0x598: ("shro", "sss"), 0x59a: ("shrdi", "sss"),
    0x59b: ("shri", "sss"), 0x59c: ("shlo", "sss"),
    0x59d: ("rotate", "sss"), 0x59e: ("shli", "sss"),
    0x5a0: ("cmpo", "ss"), 0x5a1: ("cmpi", "ss"),
    0x5a2: ("concmpo", "ss"), 0x5a3: ("concmpi", "ss"),
    0x5a4: ("cmpinco", "sss"), 0x5a5: ("cmpinci", "sss"),
    0x5a6: ("cmpdeco", "sss"), 0x5a7: ("cmpdeci", "sss"),
    0x5ac: ("scanbyte", "ss"), 0x5ad: ("bswap", "sd"),
    0x5ae: ("chkbit", "ss"), 0x5b0: ("addc", "sss"),
    0x5b2: ("subc", "sss"), 0x5b4: ("intdis", ""),
    0x5b5: ("inten", ""), 0x5cc: ("mov", "sd"),
    0x5d8: ("eshro", "sss"), 0x5dc: ("movl", "sd"),
    0x5ec: ("movt", "sd"), 0x5fc: ("movq", "sd"),
    0x600: ("synmov", "ss"), 0x601: ("synmovl", "ss"),
    0x602: ("synmovq", "ss"), 0x603: ("cmpstr", "sss"),
    0x604: ("movqstr", "sss"), 0x605: ("movstr", "sss"),
}
MEMORY = {
    0x80: "ldob", 0x82: "stob", 0x84: "bx", 0x85: "balx",
    0x86: "callx", 0x88: "ldos", 0x8a: "stos", 0x8c: "lda",
    0x90: "ld", 0x92: "st", 0x98: "ldl", 0x9a: "stl",
    0xa0: "ldt", 0xa2: "stt", 0xb0: "ldq", 0xb2: "stq",
    0xc0: "ldib", 0xc2: "stib", 0xc8: "ldis", 0xca: "stis",
}
STORES = {"stob", "stos", "st", "stl", "stt", "stq", "stib", "stis"}


@dataclass(frozen=True)
class Instruction:
    pc: int
    word: int
    size: int
    form: str
    mnemonic: str
    operands: tuple[str, ...] = ()
    flow: str = "next"
    target: int | None = None
    issue: str | None = None

    @property
    def next_pc(self) -> int:
        return self.pc + self.size

    @property
    def supported(self) -> bool:
        return self.issue is None

    def asm(self) -> str:
        suffix = (" " + ", ".join(self.operands)) if self.operands else ""
        if self.issue:
            return f".word 0x{self.word:08x} ; {self.issue}"
        return self.mnemonic + suffix


def _unknown(pc: int, word: int, why: str) -> Instruction:
    return Instruction(pc, word, 4, "unknown", "unknown",
                       flow="unknown", issue=why)


def decode(image: bytes, pc: int) -> Instruction:
    """Decode one instruction from a *mapped i960 memory image*.

    A 2-word MEMB instruction consumes its displacement word as data.
    Branches are relative to the instruction's own IP, not IP+4.
    """
    if pc % 4 or pc < 0 or pc + 4 > len(image):
        raise DecodeError(f"Unaligned or out-of-bounds IP 0x{pc:x}")
    word = struct.unpack_from("<I", image, pc)[0]
    major = word >> 24

    if major in CONTROL:
        name = CONTROL[major]
        if word & 1:
            return _unknown(pc, word, "reserved CTRL bit 0")
        if major == 0x0a:
            return Instruction(pc, word, 4, "CTRL", name, flow="return")
        if major in range(0x18, 0x20):
            return Instruction(pc, word, 4, "CTRL", name, flow="fault")
        target = (pc + signed(word & 0x00fffffc, 24)) & 0xffffffff
        flow = ("jump" if major in (0x08, 0x0b) else
                "call" if major == 0x09 else "conditional")
        return Instruction(pc, word, 4, "CTRL", name,
                           (f"0x{target:08x}",), flow, target)

    if major in COMPARE_BRANCH:
        name = COMPARE_BRANCH[major]
        first = (word >> 19) & 31
        if major in range(0x20, 0x28):
            return Instruction(pc, word, 4, "COBR", name, (reg(first),))
        src1 = str(first) if word & (1 << 13) else reg(first)
        src2 = ("sf" if word & 1 else "") + (
            str((word >> 14) & 31) if word & 1 else reg((word >> 14) & 31)
        )
        target = (pc + signed(word & 0x1ffc, 13)) & 0xffffffff
        return Instruction(pc, word, 4, "COBR", name,
                           (src1, src2, f"0x{target:08x}"),
                           "conditional", target)

    if major in MEMORY:
        name = MEMORY[major]
        dst = reg((word >> 19) & 31)
        base = reg((word >> 14) & 31)
        if word & (1 << 12):
            mode = (word >> 10) & 15
            scale = (word >> 7) & 7
            index = reg(word & 31)
            if word & 0x60 or scale > 4:
                return _unknown(pc, word, "reserved MEMB encoding")
            needs_word = mode == 5 or mode >= 12
            size = 8 if needs_word else 4
            if pc + size > len(image):
                raise DecodeError("Truncated MEMB displacement")
            disp = struct.unpack_from("<I", image, pc + 4)[0] if needs_word else 0
            def indexed():
                return f"[{index}*{1 << scale}]" if scale else f"[{index}]"
            addresses = {
                4: f"({base})",
                5: f"0x{(pc + 8 + disp) & 0xffffffff:08x}",
                7: f"({base}){indexed()}",
                12: f"0x{disp:08x}",
                13: f"0x{disp:08x}({base})",
                14: f"0x{disp:08x}{indexed()}",
                15: f"0x{disp:08x}({base}){indexed()}",
            }
            if mode not in addresses:
                return _unknown(pc, word, f"reserved MEMB addressing mode {mode}")
            address = addresses[mode]
        else:
            mode = (word >> 13) & 1
            offset = word & 0xfff
            size = 4
            address = f"0x{offset:x}({base})" if mode else f"0x{offset:x}"
        branch = name in ("bx", "balx", "callx")
        args = ((address,) if name in ("bx", "callx") else
                (address, dst) if name not in STORES else (dst, address))
        if name == "balx":
            args = (address, dst)
        flow = ("call" if name == "callx" else
                "indirect" if branch else "next")
        # Only effective-address resolution during execution can resolve MEM
        # branch targets in the general case; never invent an edge.
        return Instruction(pc, word, size, "MEMB" if word & 0x1000 else "MEMA",
                           name, args, flow)

    extended = (major << 4) | ((word >> 7) & 15)
    if extended in REGISTER:
        name, form = REGISTER[extended]
        def operand(index: int, literal: int, special: int) -> str | None:
            if literal and special:
                return None  # Reserved
            if literal:
                return str(index)
            if special:
                return f"sf{index}"
            return reg(index)
        a = operand(word & 31, (word >> 11) & 1, (word >> 5) & 1)
        b = operand((word >> 14) & 31, (word >> 12) & 1, (word >> 6) & 1)
        d = ("sf" + str((word >> 19) & 31)) if word & (1 << 13) else reg((word >> 19) & 31)
        if a is None or b is None:
            return _unknown(pc, word, "reserved REG operand mode")
        args = (() if not form else
                (a, d) if form == "sd" else
                (a, b) if form == "ss" else (a, b, d))
        return Instruction(pc, word, 4, "REG", name, args)

    return _unknown(pc, word, "opcode not yet described by independent decoder")


def read_boot_record(image: bytes) -> dict[str, int]:
    if len(image) < 16:
        raise DecodeError("Image too short for i960 reset record")
    sat, prcb, _, ip = struct.unpack_from("<4I", image, 0)
    if ip & 3:
        raise DecodeError("Invalid boot IP alignment")
    return {"sat": sat, "prcb": prcb, "initial_ip": ip}


def discover(image: bytes, entry: int, limit: int = 4096,
             additional_entries: tuple[int, ...] = ()) -> dict:
    """Conservative graph walk, not proof that every reachable byte is code.

    Direct conditional/jump/call edges are explored. Register-indirect
    transfers and unknown instructions stop the walk; no invented targets.
    """
    if limit < 1 or limit > 1_000_000:
        raise ValueError("Invalid instruction discovery limit")
    # Processor IAC reinitialization can jump to a new startup IP without
    # a normal CALL/branch edge. Explicit extra roots are research hints,
    # never inferred instruction boundaries or fabricated control flow.
    pending = deque(dict.fromkeys((entry, *additional_entries)))
    instructions: dict[int, Instruction] = {}
    rejected: dict[int, str] = {}
    occupied: dict[int, int] = {}
    edges: set[tuple[int, int, str]] = set()
    while pending and len(instructions) < limit:
        pc = pending.popleft()
        if pc in instructions or pc in rejected:
            continue
        if pc < 0 or pc + 4 > len(image) or pc % 4:
            rejected[pc] = "Target outside image or unaligned"
            continue
        if pc in occupied and occupied[pc] != pc:
            rejected[pc] = f"Target overlaps another instruction at 0x{occupied[pc]:x}"
            continue
        try:
            ins = decode(image, pc)
        except DecodeError as error:
            rejected[pc] = str(error)
            continue
        if any(byte in occupied and occupied[byte] != pc
               for byte in range(pc, pc + ins.size, 4)):
            rejected[pc] = "Overlapping instruction decoding"
            continue
        instructions[pc] = ins
        for byte in range(pc, pc + ins.size, 4):
            occupied[byte] = pc
        successors: list[tuple[int, str]] = []
        if ins.flow in ("next", "conditional", "call"):
            successors.append((ins.next_pc, "fallthrough"))
        if ins.target is not None:
            successors.append((ins.target, ins.flow))
        for target, kind in successors:
            edges.add((pc, target, kind))
            if target not in instructions and target not in rejected:
                pending.append(target)
    return {"instructions": instructions, "edges": sorted(edges),
            "rejected": rejected, "pending": len(pending),
            "limit_reached": len(instructions) >= limit and bool(pending)}
