"""Audit Boolean fixed points of a candidate LUT network with register cuts.

Connections come from an archived fitter, NOT decoded configuration switches.
DFF outputs are held boundary variables: no reset, clock, delay or sequential
semantics are inferred. All solutions, including zero/multiple, are retained.
Only counts leave the reference audit; no tables, equations or states do.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import urllib.request

from .flex8000_compare import COMMIT, DIRECTORY, MAX_FILE, REPOSITORY, git_blob_sha1
from .flex8000_fit_constraints import NODE, evaluate, names, parse_expression, parse_fitted_report, transform
from .flex8000_fit_slots import PINNED, ordered_tables, parse_fit_slots
from .flex8000_lut_tiles import CANDIDATE, candidate_tables
from .flex8000_sram import parse_sof, rcs_binary_head


@dataclass(frozen=True)
class Cell:
    name: str
    registered: bool
    slots: tuple[str | None, ...]
    expression: tuple


@dataclass(frozen=True)
class Network:
    inputs: tuple[str, ...]
    cells: tuple[Cell, ...]
    inverted: frozenset[str] = frozenset()


def validate(network: Network) -> None:
    if not 1 <= len(network.cells) <= 8 or len(network.inputs) > 8:
        raise ValueError('Network exceeds bounded eight-cell/eight-input domain')
    labels = list(network.inputs) + [c.name for c in network.cells]
    if len(labels) != len(set(labels)) or any(not isinstance(x, str) or not x for x in labels):
        raise ValueError('Ambiguous or invalid network variable')
    if not network.inverted <= {c.name for c in network.cells}:
        raise ValueError('Alias does not name a modeled cell')
    for cell in network.cells:
        if type(cell.registered) is not bool or len(cell.slots) != 4:
            raise ValueError('Cell needs four slots and explicit register classification')
        connected = [x for x in cell.slots if x is not None]
        if any(x not in labels for x in connected) or len(set(connected)) != len(connected):
            raise ValueError('Unknown or tied slot requires a different model')
        if not names(cell.expression) <= set(connected):
            raise ValueError('Equation source is not in the modeled slots')


def report_network(report: str, fit: str, device: str) -> tuple[Network, tuple[int, ...]]:
    # Reuse the existing exact target, timestamp, alias and source checks.
    tables, _ = ordered_tables(report, fit, device)
    parsed = parse_fitted_report(report, device)
    slots = parse_fit_slots(fit, device)['slots']
    equations = dict(re.findall(r'^\s*(_EQ\d+)\s*=\s*([^;]+);', report, re.M))
    aliases = dict(re.findall(r'^\s*!('+NODE+r')\s*=\s*('+NODE+r'~NOT)\s*;', report, re.M))
    definitions = {n: (kind, arg) for n, kind, arg in re.findall(
        r'^\s*('+NODE+r'(?:~NOT)?)\s*=\s*(LCELL|DFF)\s*\(([^;]*)\)\s*;', report, re.M)}
    cells = []
    for cell in parsed['cells']:
        name = f'_LC{cell["cell"]}_B1'
        kind, arg = definitions[aliases.get(name, name)]
        if kind == 'DFF':
            arg = arg.split(',')[0]  # Data only. Control pins are deliberately excluded.
        expression = parse_expression(equations.get(arg.strip(), arg))
        cells.append(Cell(name, kind == 'DFF', slots.get(name[1:], (None,)*4), expression))
    # The input list is taken from explicit FIT declarations, not inferred from
    # convenient values in the Boolean equations. Clock-only inputs remain cuts.
    inputs = tuple(sorted(re.findall(r'"([^"\r\n]+)"\s*:\s*INPUT_PIN\s*=\s*\d+\s*;', fit)))
    network = Network(inputs, tuple(cells), frozenset(aliases))
    validate(network)
    return network, tables


def feedback_sizes(network: Network) -> list[int]:
    """Exact SCCs of combinational data dependence; cut registered outputs."""
    validate(network)
    combinational = {c.name for c in network.cells if not c.registered}
    def support(expression):
        variables = sorted(names(expression))
        # Syntactic feedback can cancel, e.g. a OR NOT a. Only a variable
        # that changes the function under some assignment is a data edge.
        outputs = [evaluate(expression, {v: (n >> j) & 1 for j, v in enumerate(variables)},
                            network.inverted) for n in range(1 << len(variables))]
        return {v for j, v in enumerate(variables)
                if any(outputs[n] != outputs[n ^ (1 << j)] for n in range(len(outputs)))}
    edges = {c.name: support(c.expression) & combinational for c in network.cells if not c.registered}
    # Eight vertices maximum: reachability gives a small independent SCC method.
    reach = {}
    for node in edges:
        seen, pending = set(), list(edges[node])
        while pending:
            item = pending.pop()
            if item not in seen:
                seen.add(item); pending.extend(edges[item] - seen)
        reach[node] = seen
    remaining, sizes = set(edges), []
    while remaining:
        node = min(remaining)
        component = {x for x in remaining if x == node or (x in reach[node] and node in reach[x])}
        remaining -= component
        if len(component) > 1 or node in edges[node]:
            sizes.append(len(component))
    return sorted(sizes)


def relation(network: Network, raw_tables: tuple[int, ...], mutation_audit: bool = False) -> dict:
    """Compare full fixed-point sets, not a chosen evaluation order or first hit.

    Raw candidate bit positions use the already fixed address-XOR15/output-XOR0
    convention. One truth-table bit change can be invisible at network level;
    exact per-cell checks remain a separate mandatory gate.
    """
    validate(network)
    if len(raw_tables) != len(network.cells) or any(type(t) is not int or not 0 <= t <= 65535 for t in raw_tables):
        raise ValueError('Expected one 16-bit candidate table per cell')
    inputs, cells = network.inputs, network.cells
    registered = tuple(i for i, c in enumerate(cells) if c.registered)
    combinational = tuple(i for i, c in enumerate(cells) if not c.registered)
    boundary_count = 1 << (len(inputs) + len(registered))
    ref_sets, actual_sets = [set() for _ in range(boundary_count)], [set() for _ in range(boundary_count)]
    ref_cell_bits = []
    for cell in cells:
        table = 0
        for address in range(16):
            values = {s: (address >> j) & 1 for j, s in enumerate(cell.slots) if s is not None}
            table |= evaluate(cell.expression, values, network.inverted) << address
        ref_cell_bits.append(transform(table, (0,1,2,3), 15, 0))
    # Retain assignment records only in memory, never in a public metadata report.
    records = []
    for external in range(1 << len(inputs)):
        for state in range(1 << len(cells)):
            values = {n: (external >> j) & 1 for j, n in enumerate(inputs)}
            values.update({c.name: (state >> j) & 1 for j, c in enumerate(cells)})
            boundary = external | sum(((state >> i) & 1) << (len(inputs)+j) for j, i in enumerate(registered))
            addresses = [sum(values[s] << j for j, s in enumerate(c.slots) if s is not None) ^ 15 for c in cells]
            ref = all(values[cells[i].name] == evaluate(cells[i].expression, values, network.inverted) for i in combinational)
            mismatch = 0
            for i in combinational:
                mismatch |= (values[cells[i].name] ^ ((raw_tables[i] >> addresses[i]) & 1)) << i
            if ref: ref_sets[boundary].add(state)
            if not mismatch: actual_sets[boundary].add(state)
            records.append((boundary, state, addresses, mismatch))
    histogram = lambda sets: {str(k): v for k, v in sorted(Counter(map(len, sets)).items())}
    different = sum(a != b for a, b in zip(ref_sets, actual_sets))
    exact_bits = sum(16 - (a ^ b).bit_count() for a, b in zip(raw_tables, ref_cell_bits))
    result = {
        'cell_count': len(cells), 'combinational_cells': len(combinational),
        'register_outputs_held_as_boundary_variables': len(registered),
        'external_inputs': len(inputs), 'boundary_cases': boundary_count,
        'assignments_exhaustively_tested': len(records),
        'combinational_feedback_component_sizes': feedback_sizes(network),
        'reference_fixed_point_count_histogram': histogram(ref_sets),
        'candidate_fixed_point_count_histogram': histogram(actual_sets),
        'boundary_cases_with_different_solution_sets': different,
        'total_reference_fixed_points': sum(map(len, ref_sets)),
        'ambiguous_reference_boundaries': sum(len(s) > 1 for s in ref_sets),
        'empty_reference_boundaries': sum(not s for s in ref_sets),
        'exact_cell_bit_matches': exact_bits, 'cell_bit_comparisons': 16*len(cells),
        'all_fixed_points_match': different == 0,
        'all_cell_bits_match': exact_bits == 16*len(cells),
        'sequential_semantics_verified': False,
        'scope': 'Boolean relation with DFF outputs held; no clock/reset/delay/initial-state or physical routing inference.',
    }
    if mutation_audit:
        if not result['all_cell_bits_match']:
            raise ValueError('Mutation sensitivity needs a correctly matched baseline')
        detected = 0
        for i in range(len(cells)):
            for bit in range(16):
                altered = [set() for _ in range(boundary_count)]
                for boundary, state, addresses, mismatch in records:
                    # A mutation of a registered cell DATA LUT does not change
                    # a relation where Q is held independently. Record that limit.
                    changed = mismatch ^ ((1 << i) if i in combinational and addresses[i] == bit else 0)
                    if not changed: altered[boundary].add(state)
                detected += any(a != b for a, b in zip(ref_sets, altered))
        total = 16 * len(cells)
        result['single_bit_mutations'] = {
            'tested': total, 'detected_by_exact_cell_comparison': total,
            'detected_by_register_cut_relation': detected,
            'invisible_to_register_cut_relation': total-detected,
            'not_a_replacement_for_cell_or_sequential_validation': True,
        }
    return result


def audit_pinned_inputs(sof_rcs: bytes, report_rcs: bytes, fit_rcs: bytes) -> dict:
    for name, data in zip(PINNED, (sof_rcs, report_rcs, fit_rcs)):
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_FILE or git_blob_sha1(data) != PINNED[name]:
            raise ValueError('Pinned reference identity mismatch')
    sof = parse_sof(rcs_binary_head(sof_rcs)[1])
    rpt, fit = [rcs_binary_head(x)[1].decode('ascii') for x in (report_rcs, fit_rcs)]
    network, _ = report_network(rpt, fit, sof['device'])
    raw = candidate_tables(sof['packed'], CANDIDATE)
    return {'schema_version': 1, 'reference_commit': COMMIT, 'source_blobs': dict(PINNED),
            'candidate': CANDIDATE, 'address_xor': 15, 'output_xor': 0, 'slot_order': [0,1,2,3],
            'result': relation(network, raw, True),
            'new_independent_design': False, 'connections_from_compiler_metadata': True,
            'configuration_routing_bits_decoded': False, 'runtime_changed': False, 'model2c_complete': False}


def fetch_audit() -> dict:
    files = []
    for name in PINNED:
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}'
        with urllib.request.urlopen(url, timeout=20) as stream:
            data = stream.read(MAX_FILE+1)
        if len(data) > MAX_FILE: raise ValueError('Oversized reference')
        files.append(data)
    return audit_pinned_inputs(*files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-reference', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = fetch_audit()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, f'Feedback relation audit failed: {error}\n')
    return 0

if __name__ == '__main__': raise SystemExit(main())
