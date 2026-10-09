"""Read bounded memory-test descriptor metadata; no board identity is inferred.

HOTD1 profile follows pointers in the hash-verified original image. Descriptor
fields are reported as observed words, not invented hardware mapping rules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from .serial_contract import HOTDO_SHA256
from .i960 import decode


def u32(image: bytes, offset: int) -> int:
    if type(offset) is not int or offset < 0 or offset % 4 or offset + 4 > len(image):
        raise ValueError('Invalid mapped, word-aligned metadata pointer')
    return struct.unpack_from('<I', image, offset)[0]


def cstring(image: bytes, offset: int, limit: int = 160) -> str:
    if not 0 <= offset < len(image):
        raise ValueError('String pointer outside image')
    stop = image.find(b'\0', offset, min(offset + limit, len(image)))
    if stop < 0:
        raise ValueError('Unterminated or oversized display text')
    data = image[offset:stop]
    if not data or any(c < 32 or c > 126 for c in data):
        raise ValueError('Display string is not bounded printable ASCII')
    return data.decode('ascii')


def descriptor_groups(image: bytes, pointer_table: int) -> list[dict]:
    """Bounded table-of-tables reader, independently testable on artificial data."""
    groups, seen, entries = [], set(), 0
    for n in range(33):
        pointer = u32(image, pointer_table + 4*n)
        if not pointer:
            return groups
        if n == 32 or pointer in seen:
            raise ValueError('Unterminated/duplicate descriptor-group pointer')
        seen.add(pointer)
        group = {'table_address': hex(pointer), 'descriptors': []}
        for j in range(65):
            site = pointer + 24*j
            label_descriptor = u32(image, site)
            if not label_descriptor:
                break
            if j == 64 or entries >= 256:
                raise ValueError('Descriptor limit reached without terminator')
            label = cstring(image, u32(image, label_descriptor + 8))
            # Only chip-designator metadata is exported, not game font/text assets.
            chips = [int(x) for x in re.findall(r'\bIC\s*(\d+)\b', label)]
            if not chips and label.strip():
                raise ValueError('Expected IC-designator or explicitly blank display record')
            kind, lanes, mask, start, span = [u32(image, site+4*i) for i in range(1,6)]
            if not span or start + span > 0x100000000:
                raise ValueError('Invalid candidate memory-test span')
            group['descriptors'].append({'descriptor_address': hex(site),
                'chip_designators': chips, 'display_label_blank': not label.strip(),
                'kind_field': kind, 'count_field': lanes,
                'mask_field': hex(mask), 'address_field': hex(start), 'length_field': hex(span)})
            entries += 1
        else:
            raise ValueError('Missing group sentinel')
        groups.append(group)
    raise ValueError('Missing pointer-table sentinel')


def audit_hotdo(image: bytes) -> dict:
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Not the verified original hotdo i960 image')
    # Menu list -> display descriptor -> bounded title string.
    label = cstring(image, u32(image, u32(image, 0xa8830) + 8))
    if label != 'MEMORY TEST':
        raise ValueError('Unexpected menu title')
    groups = descriptor_groups(image, 0x8ae0)
    sites = []
    for pc in (0x6b4, 0x8b88, 0x8ba0):
        ins = decode(image, pc)
        if ins.mnemonic != 'st' or ins.size != 8 or ((ins.word >> 10) & 15) != 12 \
                or u32(image, pc+4) != 0x00f80000:
            raise ValueError('Expected absolute board store not found')
        sites.append({'site': hex(pc), 'source_register_index': (ins.word >> 19) & 31})
    return {'schema_version': 1, 'image_sha256': HOTDO_SHA256,
        'evidence_level': 'static_pointer_and_instruction_analysis',
        'menu_title': label, 'menu_pointer_table': '0xa8830',
        'test_pointer_table': '0x8ae0', 'group_count': len(groups),
        'descriptor_count': sum(len(g['descriptors']) for g in groups),
        'store_sites': sites, 'groups': groups,
        'interpretation_boundary': 'Memory-test context, not proof of executed paths or physical 0x00F80000 device identity.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        if args.image.stat().st_size != 0x200000:
            raise ValueError('Expected mapped 2-MiB original CPU image')
        report = audit_hotdo(args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(f'Wrote {report["descriptor_count"]} static descriptor records; device identity remains unresolved.')
    except (OSError, ValueError) as error:
        p.exit(2, f'Memory-test audit failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
