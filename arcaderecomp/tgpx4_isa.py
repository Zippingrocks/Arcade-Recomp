"""Document-backed structural decoding for Fujitsu MB86235 instructions.

Fujitsu's Hot Chips VII MB86235 presentation documents one 64-bit format:
Type 1 has a three-bit ``000`` format tag followed by independent ALU,
multiply, and transfer fields.  It does not publish enough bit-level opcode
tables to interpret those fields, so this module deliberately stops at the
documented partition instead of guessing operations.
"""
from __future__ import annotations

from dataclasses import dataclass


INSTRUCTION_BITS = 64
FORMAT_TAG_SHIFT = 61
FORMAT_TAG_BITS = 3
TYPE1_TAG = 0b000

TYPE1_ALU_SHIFT = 42
TYPE1_ALU_BITS = 19
TYPE1_MUL_SHIFT = 27
TYPE1_MUL_BITS = 15
TYPE1_TRANSFER_SHIFT = 0
TYPE1_TRANSFER_BITS = 27


class DecodeError(ValueError):
    """The word is malformed or its instruction format is undocumented."""


def _mask(bits: int) -> int:
    return (1 << bits) - 1


@dataclass(frozen=True)
class Type1Instruction:
    """Raw documented Type-1 fields, without invented operation semantics."""

    raw: int
    format_tag: int
    alu_field: int
    mul_field: int
    transfer_field: int


def decode_type1(word: int) -> Type1Instruction:
    """Partition one Fujitsu-documented Type-1 64-bit instruction word.

    The returned integers are opaque fields.  In particular, this function
    does not claim that a field value names XOR, FADD, FMUL, MOV1, or any
    other operation shown in the presentation's assembly example.
    """
    if type(word) is not int or not 0 <= word < (1 << INSTRUCTION_BITS):
        raise DecodeError("instruction must be an unsigned 64-bit integer")

    tag = (word >> FORMAT_TAG_SHIFT) & _mask(FORMAT_TAG_BITS)
    if tag != TYPE1_TAG:
        raise DecodeError(
            f"undocumented MB86235 instruction format tag 0b{tag:03b}")

    return Type1Instruction(
        raw=word,
        format_tag=tag,
        alu_field=(word >> TYPE1_ALU_SHIFT) & _mask(TYPE1_ALU_BITS),
        mul_field=(word >> TYPE1_MUL_SHIFT) & _mask(TYPE1_MUL_BITS),
        transfer_field=(word >> TYPE1_TRANSFER_SHIFT) &
        _mask(TYPE1_TRANSFER_BITS),
    )
