"""Constrain a candidate LUT layout with fitted-report polarities.

This does NOT recover FPGA routing, clocks or pins. It tests two explicit
interpretations of one archival fitted report against one pinned SOF.
Candidate coordinates stay fixed; only bounded bit conventions are tested.
No reference configuration bytes or truth tables are exported.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import re
import urllib.request

from .flex8000_compare import COMMIT, DIRECTORY, MAX_FILE, REPOSITORY, git_blob_sha1
from .flex8000_sram import parse_sof, rcs_binary_head
from .flex8000_lut_tiles import CANDIDATE, PINNED, candidate_tables

NAME = r'/?[A-Za-z_][A-Za-z0-9_/~]*'
NODE = r'_LC[1-8]_[AB](?:[1-9]|1[0-3])'
PERMUTATIONS = tuple(itertools.permutations(range(4)))


def parse_expression(text: str):
    """Strict small Boolean grammar: !, &, #, parentheses and net names."""
    if not isinstance(text, str) or not 0 < len(text) <= 4096:
        raise ValueError('Expression length invalid')
    tokens, pos = [], 0
    while pos < len(text):
        m = re.match(r'\s*(?:(' + NAME + r')|([!&#()]))', text[pos:])
        if not m:
            if text[pos:].isspace(): break
            raise ValueError('Unknown Boolean expression token')
        tokens.append(m[1] or m[2]); pos += m.end()
        if len(tokens) > 256: raise ValueError('Expression token limit')
    index = 0
    def atom(depth=0):
        nonlocal index
        if depth > 32 or index >= len(tokens): raise ValueError('Incomplete/deep expression')
        token = tokens[index]; index += 1
        if token == '!': return ('not', atom(depth+1))
        if token == '(':
            result = disjunction(depth+1)
            if index >= len(tokens) or tokens[index] != ')': raise ValueError('Unclosed parenthesis')
            index += 1
            return result
        if not re.fullmatch(NAME, token): raise ValueError('Expected net identifier')
        return ('name', token)
    def conjunction(depth=0):
        nonlocal index
        result = atom(depth)
        while index < len(tokens) and tokens[index] == '&':
            index += 1; result = ('and', result, atom(depth))
        return result
    def disjunction(depth=0):
        nonlocal index
        result = conjunction(depth)
        while index < len(tokens) and tokens[index] == '#':
            index += 1; result = ('or', result, conjunction(depth))
        return result
    result = disjunction()
    if index != len(tokens): raise ValueError('Trailing expression tokens')
    return result


def names(ast):
    if ast[0] == 'name': return set() if ast[1] in ('VCC','GND') else {ast[1]}
    return set().union(*(names(a) for a in ast[1:]))


def evaluate(ast, values, inverted):
    op = ast[0]
    if op == 'name':
        n = ast[1]
        if n == 'VCC': return 1
        if n == 'GND': return 0
        return values[n] ^ (n in inverted)
    if op == 'not': return 1 ^ evaluate(ast[1],values,inverted)
    a,b = (evaluate(x,values,inverted) for x in ast[1:])
    return (a & b) if op == 'and' else (a | b)


def table_from_ast(ast, inverted=frozenset()):
    inputs = sorted(names(ast))
    if len(inputs) > 4: raise ValueError('More than four LUT-data variables')
    table = sum(evaluate(ast,dict(zip(inputs,((n>>j)&1 for j in range(len(inputs))))),inverted)<<n
                for n in range(16))
    return table, len(inputs)


def parse_fitted_report(report: str, device: str, bank: str = 'B1') -> dict:
    """Inspect explicit LCELL/DFF-data definitions; do not evaluate sequential logic."""
    if not isinstance(report,str) or not 0 < len(report) <= MAX_FILE:
        raise ValueError('Invalid fitted-report size')
    if not re.fullmatch(r'[AB](?:[1-9]|1[0-3])',bank): raise ValueError('Invalid LAB name')
    targets = re.findall(r'^\s*Device:\s*(\S+)\s*$',report,re.M)
    if targets != [device]: raise ValueError('Missing, ambiguous or mismatched report device')
    aliases = {}
    for src,dst in re.findall(r'^\s*!('+NODE+r')\s*=\s*('+NODE+r'~NOT)\s*;',report,re.M):
        if src in aliases or dst != src+'~NOT': raise ValueError('Unsupported inversion alias')
        aliases[src] = dst
    equations = {}
    for name,text in re.findall(r'^\s*(_EQ\d+)\s*=\s*([^;]+);',report,re.M):
        if name in equations: raise ValueError('Duplicate equation')
        equations[name] = text
    definitions = {}
    for node,kind,args in re.findall(r'^\s*('+NODE+r'(?:~NOT)?)\s*=\s*(LCELL|DFF)\s*\(([^;]*)\)\s*;',report,re.M):
        if node in definitions: raise ValueError('Duplicate fitted-cell definition')
        definitions[node] = (kind,args)
    cells = []
    for index in range(1,9):
        logical = f'_LC{index}_{bank}'
        physical = aliases.get(logical,logical)
        if physical not in definitions: raise ValueError('Fitted cell definition absent')
        kind,args = definitions[physical]
        if kind == 'DFF':
            parts = args.split(',')
            if len(parts) != 4: raise ValueError('Unsupported DFF argument list')
            args = parts[0]  # ONLY the data expression, not clocks/clear/preset.
        expr = equations.get(args.strip(),args)
        if re.search(r'\b_EQ\d+',expr): raise ValueError('Unresolved equation reference')
        ast = parse_expression(expr)
        for name in names(ast):
            if name.endswith('~NOT'): raise ValueError('Explicit alias-input form not modeled')
            if re.match(r'_LC',name) and name not in definitions and name not in aliases:
                raise ValueError('Referenced logic cell has no fitted definition')
        direct,n = table_from_ast(ast)
        normalized,_ = table_from_ast(ast,frozenset(aliases))
        cells.append({'cell':index,'kind':kind,'input_count':n,
                      'logical_table':direct,'normalized_table':normalized,
                      'inverted_output_alias':logical in aliases})
    return {'device':device,'bank':bank,'cells':cells,
            'clock_or_routing_decoded':False}


@lru_cache(maxsize=8192)
def transform(table: int, permutation: tuple[int,...], address_xor: int, output_xor: int) -> int:
    """raw[x] = logical[permute(x XOR common_address_mask)] XOR common_output_bit."""
    if type(table) is not int or not 0 <= table <= 65535 or \
       len(permutation)!=4 or any(type(i) is not int for i in permutation) or set(permutation)!=set(range(4)) or \
       type(address_xor) is not int or not 0 <= address_xor < 16 or \
       type(output_xor) is not int or output_xor not in (0,1):
        raise ValueError('Invalid four-input transform')
    value=0
    for x in range(16):
        address=sum((((x^address_xor)>>permutation[j])&1)<<j for j in range(4))
        value |= (((table>>address)&1)^output_xor)<<x
    return value


def common_conventions(raw_tables, expected_tables) -> dict:
    """Require one common address polarity mask/output polarity for every cell.

    Per-cell input permutations are allowed because routing is unknown. A
    surviving mapping is a hypothesis, not a physical pin assignment.
    """
    if len(raw_tables)!=8 or len(expected_tables)!=8:
        raise ValueError('Expected exactly eight candidate/reference cells')
    for t in (*raw_tables,*expected_tables):
        if type(t) is not int or not 0<=t<=65535: raise ValueError('Bad truth table')
    survivors=[]
    for output_xor in (0,1):
        for address_xor in range(16):
            counts=[]
            for raw,expected in zip(raw_tables,expected_tables):
                count=sum(transform(expected,p,address_xor,output_xor)==raw for p in PERMUTATIONS)
                counts.append(count)
            if all(counts):
                survivors.append({'address_xor':address_xor,'output_xor':output_xor,
                                  'per_cell_permutation_counts':counts})
    return {'common_convention_count':len(survivors),'conventions':survivors,
            'tested_common_conventions':32,'input_permutations_per_cell':24,
            'physical_input_assignment_verified':False}


def audit_pinned_inputs(sof_rcs: bytes, report_rcs: bytes) -> dict:
    for name,data in (('testmux.sof,v',sof_rcs),('testmux.rpt,v',report_rcs)):
        if git_blob_sha1(data)!=PINNED[name]: raise ValueError('Reference blob identity mismatch')
    sof=parse_sof(rcs_binary_head(sof_rcs)[1])
    report=rcs_binary_head(report_rcs)[1].decode('ascii')
    fitted=parse_fitted_report(report,sof['device'])
    raw=candidate_tables(sof['packed'],CANDIDATE)
    results={label:common_conventions(raw,tuple(c[key] for c in fitted['cells']))
             for label,key in (('logical_report_signals','logical_table'),
                               ('normalized_fitted_output_aliases','normalized_table'))}
    return {'schema_version':1,'reference_commit':COMMIT,
            'source_blobs':{name:PINNED[name] for name in ('testmux.sof,v','testmux.rpt,v')},
            'configuration_sha256':hashlib.sha256(sof['packed']).hexdigest(),
            'candidate':CANDIDATE,'cell_count':8,
            'registered_data_cells':sum(c['kind']=='DFF' for c in fitted['cells']),
            'inverted_output_aliases':sum(c['inverted_output_alias'] for c in fitted['cells']),
            'models':results,'netlist_recovered':False,'runtime_changed':False,
            'scope':'Fixed candidate and one archival SOF/report pair; no new independent circuit or controlled rebuild.'}


def fetch_audit() -> dict:
    data=[]
    for name in ('testmux.sof,v','testmux.rpt,v'):
        url=f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}'
        with urllib.request.urlopen(url,timeout=20) as response: payload=response.read(MAX_FILE+1)
        if len(payload)>MAX_FILE: raise ValueError('Oversized pinned input')
        data.append(payload)
    return audit_pinned_inputs(*data)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch-reference',action='store_true',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        result=fetch_audit()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    except (ValueError,OSError,UnicodeError) as error:
        p.exit(2,f'Fitted constraint audit failed: {error}\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
