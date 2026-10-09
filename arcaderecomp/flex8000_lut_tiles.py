"""Candidate two-dimensional LUT layouts, NOT a recovered FPGA circuit.

One archival reference supplies function classes, not a controlled rebuild.
Only metadata is exported. No candidate changes the game hardware model.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import urllib.request

from .flex8000_lut_probe import TABLES, integer, npn_orbit, vector
from .flex8000_sram import (TOTAL_BITS, parse_sof, rcs_binary_head,
                            serial_to_sof_data)
from .flex8000_compare import COMMIT, DIRECTORY, REPOSITORY, MAX_FILE, git_blob_sha1
from .serial_contract import HOTDO_SHA256, UPLOAD_BEGIN, UPLOAD_END

PITCHES = (16,26,32,52,53,64,104,106,128,176,177,178,208,212,256,354,424,512,708)
COLUMN_STEPS = (1,2,4,8,13,16,26,53,104,177,212)
# These assignments are abstract classes from the pinned testmux report.
# Discovery uses cells 1,2,3,7; validation uses the other four cells.
CELL_CLASSES = (0,1,2,3,3,4,2,3)
PINNED = {
    'testmux.sof,v': '4bd945df501d848d9fc4fd512945336ec7c24fca',
    'testmux.rpt,v': '88deb079d565b038b1bc4a71e015fd324dddd3ab',
    'buff_with_clk.sof,v': '224eeb4b8023f9fc0a16166f9e72d224ba32b57b',
    'buff_with_clk.rpt,v': '5baeecf6381f5a8d746da4c99b56875a52e4fa75',
}
# Candidate coordinates are in the SOF bit vector, not physical SRAM axes.
CANDIDATE = {'first_bit': 22138, 'cell_stride': 1416,
             'rows': 8, 'row_pitch': 177, 'column_step': 1}


@lru_cache(maxsize=1)
def classes() -> tuple[frozenset[int], ...]:
    return tuple(npn_orbit(t) for t in TABLES)


def tile_offsets(rows: int, pitch: int, column_step: int) -> tuple[int, ...]:
    if type(rows) is not int or rows not in (2,4,8):
        raise ValueError('A tile has 2, 4, or 8 rows and exactly 16 bits')
    integer(pitch, 1, 708, 'row pitch')
    integer(column_step, 1, 212, 'column step')
    offsets = tuple(r*pitch+c*column_step for r in range(rows) for c in range(16//rows))
    if len(set(offsets)) != 16:
        raise ValueError('Tile addresses overlap')
    return offsets


def shapes() -> tuple[tuple[int, int, int], ...]:
    result = []
    for rows in (2,4,8):
        for pitch in PITCHES:
            for step in COLUMN_STEPS:
                try:
                    tile_offsets(rows,pitch,step)
                except ValueError:
                    continue
                result.append((rows,pitch,step))
    return tuple(result)


def _indices(mask: int):
    # Enumerate per byte instead of repeatedly copying a 37k-bit integer.
    for offset, byte in enumerate(mask.to_bytes((mask.bit_length()+7)//8, 'little')):
        while byte:
            low = byte & -byte
            yield 8*offset + low.bit_length()-1
            byte ^= low


def class_positions(packed: bytes, width: int, offsets: tuple[int,...]) -> tuple[set[int], ...]:
    """Exact class matches; parallel population counts only prefilter candidates.

    Every retained candidate is checked against the complete NPN truth class.
    The population filter is not used as evidence that a truth table matches.
    """
    data = vector(packed,width)
    if len(offsets) != 16 or any(type(n) is not int or n < 0 or n >= width for n in offsets) \
            or len(set(offsets)) != 16:
        raise ValueError('Expected 16 distinct mapped nonnegative bit offsets')
    n = width-max(offsets)
    valid = (1 << n)-1
    sums = [0]*5
    # Bit position j in each wide integer describes candidate start j.
    for offset in offsets:
        carry = (data >> offset) & valid
        for i in range(5):
            old = sums[i]
            sums[i] ^= carry
            carry &= old
            if not carry:
                break
    def population_mask(number):
        result = valid
        for i, plane in enumerate(sums):
            result &= plane if number & (1 << i) else ~plane
        return result
    bits = [(data >> i) & 1 for i in range(width)]
    result = []
    for group in classes():
        counts = {value.bit_count() for value in group}
        selected = 0
        for count in counts:
            selected |= population_mask(count)
        # Constant-class truth tables require no further positional ordering.
        if counts == {0,16}:
            result.append(set(_indices(selected)))
            continue
        positions = set()
        for start in _indices(selected):
            value = sum(bits[start+offset] << i for i,offset in enumerate(offsets))
            if value in group:
                positions.add(start)
        result.append(positions)
    return tuple(result)


def scan_tiles(packed: bytes, width: int = TOTAL_BITS,
               domain: tuple[tuple[int,int,int], ...] | None = None) -> dict:
    vector(packed,width)
    domain = shapes() if domain is None else domain
    if not 1 <= len(domain) <= 1024 or len(set(domain)) != len(domain):
        raise ValueError('Require 1..1024 unique, bounded tile shapes')
    results = []
    for rows,pitch,column_step in domain:
        offsets=tile_offsets(rows,pitch,column_step)
        if max(offsets) >= width:
            raise ValueError('Tile does not fit declared vector')
        positions=class_positions(packed,width,offsets)
        four, eight = 0, []
        # Derive all possible signed cell strides from cells 1 and 3.
        # Unlike the previous scanner this imposes no +/-512 stride ceiling.
        for first in sorted(positions[0]):
            for third in sorted(positions[2]):
                delta=third-first
                if not delta or delta % 2:
                    continue
                stride=delta//2
                if first+stride not in positions[1] or first+6*stride not in positions[2]:
                    continue
                four+=1
                if any(first+i*stride not in positions[group]
                       for i,group in enumerate(CELL_CLASSES)):
                    continue
                locations=[first+i*stride+o for i in range(8) for o in offsets]
                if len(set(locations)) != 128:
                    continue  # One configuration bit cannot be two unrelated LUT cells.
                eight.append({'first_bit':first,'cell_stride':stride})
        results.append({'rows':rows,'row_pitch':pitch,'column_step':column_step,
                        'class_window_counts':[len(p) for p in positions],
                        'four_cell_candidates':four,'eight_cell_candidates':eight})
    return {'schema_version':1,'width':width,'shape_count':len(domain),
            'four_cell_candidates':sum(r['four_cell_candidates'] for r in results),
            'eight_cell_candidate_count':sum(len(r['eight_cell_candidates']) for r in results),
            'results':results,'physical_layout_verified':False,
            'scope':'Bounded rectangular tiles and a uniform signed cell stride; archival function-class evidence only.'}


def candidate_tables(packed: bytes, candidate: dict, width: int = TOTAL_BITS) -> tuple[int,...]:
    data=vector(packed,width)
    if set(candidate) != {'first_bit','cell_stride','rows','row_pitch','column_step'}:
        raise ValueError('Unexpected candidate fields')
    first=integer(candidate['first_bit'],0,width-1,'first bit')
    stride=integer(candidate['cell_stride'],-width,width,'cell stride')
    if stride == 0:
        raise ValueError('Zero cell stride')
    offsets=tile_offsets(candidate['rows'],candidate['row_pitch'],candidate['column_step'])
    all_bits=[first+i*stride+o for i in range(8) for o in offsets]
    if min(all_bits)<0 or max(all_bits)>=width or len(set(all_bits))!=128:
        raise ValueError('Candidate escapes vector or aliases cells')
    return tuple(sum(((data>>(first+i*stride+o))&1)<<j for j,o in enumerate(offsets)) for i in range(8))


def target_agrees(sof: dict, report: str) -> bool:
    # Explicit device declaration; a list of supported parts is insufficient.
    return any(line.strip() == 'Device: '+sof['device'] for line in report.splitlines())


def reference_audit() -> dict:
    files={}
    for name,expected in PINNED.items():
        url=f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}'
        with urllib.request.urlopen(url,timeout=20) as response:
            data=response.read(MAX_FILE+1)
        if len(data)>MAX_FILE or git_blob_sha1(data)!=expected:
            raise ValueError('Pinned reference identity mismatch')
        files[name]=rcs_binary_head(data)[1]
    positive=parse_sof(files['testmux.sof,v'])
    report=files['testmux.rpt,v'].decode('ascii')
    if not target_agrees(positive,report) or 'Total logic cells required:                      8' not in report:
        raise ValueError('Reference fitted report does not match target/cell count')
    result=scan_tiles(positive['packed'])
    matches=[dict(rows=r['rows'],row_pitch=r['row_pitch'],column_step=r['column_step'],**c)
             for r in result['results'] for c in r['eight_cell_candidates']]
    # Expected discovery is a regression guard, never a manufactured result.
    if matches != [CANDIDATE]:
        raise ValueError('Measured candidate differs; investigate rather than silently refit')
    other=parse_sof(files['buff_with_clk.sof,v'])
    other_report=files['buff_with_clk.rpt,v'].decode('ascii')
    if target_agrees(other,other_report):
        raise ValueError('Previously incompatible validation pair changed unexpectedly')
    result.update(source_commit=COMMIT,source_blobs=PINNED,
                  configuration_sha256=hashlib.sha256(positive['packed']).hexdigest(),
                  reference_device=positive['device'],candidates=matches,
                  separate_design_validation='REJECTED: buff_with_clk report targets EPM5130QC; SOF targets EPF8282ALC84-2.',
                  independent_compiler_validation=False,netlist_recovered=False)
    return result


def original_metadata(image: bytes) -> dict:
    if len(image)!=0x200000 or hashlib.sha256(image).hexdigest()!=HOTDO_SHA256:
        raise ValueError('Not the hash-verified original hotdo CPU image')
    packed=serial_to_sof_data(image[UPLOAD_BEGIN:UPLOAD_END])
    tables=candidate_tables(packed,CANDIDATE)
    # Do not export original truth-table/configuration data or inferred nets.
    return {'schema_version':1,'image_sha256':HOTDO_SHA256,
            'configuration_sha256':hashlib.sha256(packed).hexdigest(),
            'candidate':CANDIDATE,'selected_bits':128,'candidate_table_count':len(tables),
            'sampled_coordinate_extraction_completed':True,
            'original_function_equivalence_verified':False,
            'netlist_recovered':False,'runtime_changed':False,
            'interpretation':'Only conditional coordinates transferred from a non-Sega reference; not verified HOTD1 LUT meanings.'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fetch-reference',action='store_true')
    mode.add_argument('--image',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.image:
            if args.output.resolve()==args.image.resolve():
                raise ValueError('Output must not overwrite input')
            if args.image.stat().st_size!=0x200000:
                raise ValueError('Expected 2-MiB input')
            result=original_metadata(args.image.read_bytes())
        else:
            result=reference_audit()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('Wrote candidate metadata. No FPGA circuit or hardware replies recovered.')
    except (OSError,ValueError,UnicodeError,TypeError) as error:
        parser.exit(2,f'Tile audit failed: {error}\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
