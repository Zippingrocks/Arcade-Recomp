"""Controlled EPF8282 probe coverage and affine-encoding hypothesis tests.

This infers mathematical relations on supplied compiler outputs, NOT physical
LUT locations or circuitry. No actual controlled compiler corpus is bundled.
The original 23-source plan is preserved; --plan emits 26 UNCOMPILED sources.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from .flex8000_lut_probe import (HOLDOUTS, ahdl, correlate, integer, probe_plan,
                                read_corpus, vector)
from .flex8000_sram import TOTAL_BITS

# Three complements of distinct minterms cover every pair's 11 assignment:
# any pair contains at most two of the three omitted indices. All functions
# still depend on all four Boolean inputs; no constant-function probe is used.
ADDED_HOLDOUTS = (0xFFFE, 0xFFFD, 0xFFFB)
STRONG_HOLDOUTS = HOLDOUTS + ADDED_HOLDOUTS


def sample_coverage(tables: list[int]) -> dict:
    """Coverage of PAIRS OF TRUTH-TABLE BITS, not pairs of FPGA input pins.

    Pair coverage is a necessary diagnostic, never proof against all nonlinear
    confounders. Any finite experiment leaves untested functions possible.
    """
    if not isinstance(tables, list) or not 1 <= len(tables) <= 64:
        raise ValueError('Expected 1..64 truth-table samples')
    for truth in tables:
        integer(truth, 0, 65535, 'truth table')
    unique = sorted(set(tables))
    missing = []
    for a, b in itertools.combinations(range(16), 2):
        observed = {((t >> a) & 1) | (((t >> b) & 1) << 1) for t in unique}
        if len(observed) != 4:
            missing.append({'truth_bits': [a, b],
                            'missing_assignments': sorted(set(range(4)) - observed)})
    # Rank over GF(2) of rows [constant=1, t_0, ..., t_15].
    pivots: dict[int, int] = {}
    for truth in unique:
        row = (truth << 1) | 1
        while row:
            pivot = row.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = row
                break
            row ^= pivots[pivot]
    return {'unique_truth_tables': len(unique), 'affine_design_rank': len(pivots),
            'affine_unknowns': 17, 'pair_count': 120,
            'fully_observed_pairs': 120 - len(missing), 'incomplete_pairs': missing,
            'pair_assignment_encoding': 'bit0=lower-index truth bit; bit1=higher-index truth bit',
            'all_pair_assignments_observed': not missing,
            'nonlinear_behaviors_excluded': False}


def _checked_inputs(training, repeat, heldouts, width):
    if len(training) != 16 or not 4 <= len(heldouts) <= 32:
        raise ValueError('Require 16 minterms and 4..32 independent holdouts')
    values = [vector(data, width) for data in training]
    if vector(repeat, width) != values[0]:
        raise ValueError('Repeated baseline differs; do not infer a controlled mapping')
    seen, checked = set(), []
    for truth, data in heldouts:
        integer(truth, 0, 65535, 'holdout truth table')
        if truth in seen or truth in {1 << n for n in range(16)}:
            raise ValueError('Duplicate holdout or holdout reused from training')
        seen.add(truth)
        checked.append((truth, vector(data, width)))
    return values, checked


def affine_models(training: list[bytes], repeat: bytes,
                  heldouts: list[tuple[int, bytes]], width=TOTAL_BITS,
                  max_examples: int = 64) -> dict:
    """Fit both affine intercept choices; evaluate holdouts without refitting.

    For a config bit with minterm signature s, the only two affine candidates
    are parity(s & truth), and 1 XOR parity((s XOR 0xFFFF) & truth).
    Odd-weight holdouts cannot distinguish them; even-weight holdouts can.
    A unique surviving formula is NOT proof of an affine physical encoding.
    """
    integer(max_examples, 0, 256, 'maximum reported examples')
    values, checked = _checked_inputs(training, repeat, heldouts, width)
    mask = (1 << width) - 1
    live_zero, live_one = mask, mask
    for truth, observed in checked:
        predicted = 0
        for n, value in enumerate(values):
            if (truth >> n) & 1:
                predicted ^= value
        live_zero &= mask ^ (predicted ^ observed)
        other = predicted ^ (mask if truth.bit_count() % 2 == 0 else 0)
        live_one &= mask ^ (other ^ observed)
    counts = {key: 0 for key in ('constant_on_fitted_model', 'one_truth_bit_model',
                                 'multiple_truth_bit_model', 'ambiguous_intercept',
                                 'no_affine_model_on_samples')}
    examples, digest = [], hashlib.sha256()
    term_counts = [0] * 17
    for pos in range(width):
        viable = [c for c, survivors in ((0, live_zero), (1, live_one)) if survivors >> pos & 1]
        signature = sum(((value >> pos) & 1) << n for n, value in enumerate(values))
        models = [{'truth_mask': signature ^ (65535 if c else 0), 'xor_constant': c}
                  for c in viable]
        if len(models) == 2:
            category = 'ambiguous_intercept'
        elif not models:
            category = 'no_affine_model_on_samples'
        else:
            terms = models[0]['truth_mask'].bit_count()
            term_counts[terms] += 1
            category = ('constant_on_fitted_model' if not terms else
                        'one_truth_bit_model' if terms == 1 else 'multiple_truth_bit_model')
        counts[category] += 1
        # A deterministic commitment to the full set without dumping private
        # configuration values or thousands of speculative physical labels.
        encoded = json.dumps([pos, models], separators=(',', ':'), sort_keys=True).encode('ascii')
        digest.update(encoded + b'\n')
        if category != 'constant_on_fitted_model' and len(examples) < max_examples:
            examples.append({'configuration_bit': pos, 'status': category, 'models': models})
    coverage = sample_coverage([1 << n for n in range(16)] + [t for t, _ in checked])
    return {'schema_version': 1, 'evidence_level': 'affine_family_consistency_on_supplied_samples',
            'vector_bits': width, 'training_designs': 16, 'repeat_matches': True,
            'heldout_designs': len(checked), 'counts': counts,
            'unique_model_term_count_histogram': term_counts,
            'coverage': coverage, 'examples': examples,
            'examples_truncated': width - counts['constant_on_fitted_model'] > len(examples),
            'all_candidate_models_sha256': digest.hexdigest(),
            'formula': 'output = XOR_constant XOR parity(truth_table AND truth_mask)',
            'physical_lut_identified': False, 'physical_routing_verified': False,
            'logic_netlist_recovered': False, 'hardware_validation': False,
            'warning': 'Passing finite samples only selects a model in this hypothesis family; nonlinear alternatives and changed fitting can still explain it.'}


def stronger_plan() -> dict:
    plan = probe_plan()
    plan['schema_version'] = 2
    plan['cases'] += [{'name': f'holdout_pair_{n:02d}', 'role': 'holdout', 'truth': table}
                      for n, table in enumerate(ADDED_HOLDOUTS)]
    plan['source_count'] = len(plan['cases'])
    plan['coverage'] = sample_coverage([c['truth'] for c in plan['cases']])
    plan['unchanged_original_holdouts'] = list(HOLDOUTS)
    plan['additional_pair_probes'] = list(ADDED_HOLDOUTS)
    plan['requirements'].append('Pair coverage detects one class of confounders, not all possible nonlinear encodings.')
    return plan


def _synthetic_vectors(tables, nonlinear: bool) -> list[bytes]:
    # Only bit 37 varies. Other configuration positions are deliberately zero.
    # f(t)=t_2 XOR (t_0 AND t_1) is wrong as a direct t_2 mapping, yet the
    # old test plan never activated t_0 AND t_1, making it invisible there.
    result = []
    for table in tables:
        value = ((table >> 2) & 1) ^ (int((table & 3) == 3) if nonlinear else 0)
        result.append((value << 37).to_bytes(8, 'little'))
    return result


def self_audit() -> dict:
    training = _synthetic_vectors([1 << n for n in range(16)], True)
    weak = list(zip(HOLDOUTS, _synthetic_vectors(HOLDOUTS, True)))
    strong = list(zip(STRONG_HOLDOUTS, _synthetic_vectors(STRONG_HOLDOUTS, True)))
    weak_direct = correlate(training, training[0], weak, 64)
    strong_direct = correlate(training, training[0], strong, 64)
    false_positive = weak_direct['bits'][2]
    rejected = strong_direct['bits'][2]
    if false_positive['status'] != 'unique_in_corpus' or rejected['status'] != 'not_identified':
        raise ValueError('Counterexample did not reproduce; do not write a claimed result')
    weak_affine = affine_models(training, training[0], weak, 64)
    strong_affine = affine_models(training, training[0], strong, 64)
    return {'schema_version': 1, 'evidence_level': 'reproduced_synthetic_counterexample',
            'original_23_source_plan_coverage': weak_affine['coverage'],
            'new_26_source_plan_coverage': strong_affine['coverage'],
            'counterexample': 'configuration_bit_37 = truth_bit_2 XOR (truth_bit_0 AND truth_bit_1)',
            'old_direct_mapper_result_for_truth_bit_2': false_positive,
            'extended_mapper_result_for_truth_bit_2': rejected,
            'old_affine_result_counts': weak_affine['counts'],
            'extended_affine_result_counts': strong_affine['counts'],
            'old_plan_still_reproducible': True,
            'compiled_real_corpus_used': False, 'sega_data_used': False,
            'runtime_changed': False, 'model2c_complete': False}


def load_affine_corpus(path: Path) -> dict:
    corpus = read_corpus(path)
    result = affine_models(corpus['training'], corpus['repeat'], corpus['heldouts'])
    result.update(device=corpus['device'], source_hashes=corpus['identities'],
                  compiler_executed_by_this_tool=False)
    return result


def write_plan(path: Path) -> None:
    if path.exists():
        raise ValueError('Plan output must be a new directory')
    path.mkdir(parents=True)
    plan = stronger_plan()
    for case in plan['cases']:
        folder = path / case['name']
        folder.mkdir()
        (folder / 'lut_probe.tdf').write_text(ahdl(case['truth']), encoding='ascii')
    (path / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--self-audit', action='store_true')
    g.add_argument('--plan', type=Path)
    g.add_argument('--corpus', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        if args.plan:
            if args.output is not None:
                raise ValueError('--output is not used with --plan')
            write_plan(args.plan)
            print('Created 26 ORIGINAL UNCOMPILED sources; no bit mapping or physical fit is claimed.')
        else:
            if args.output is None:
                raise ValueError('--output is required')
            if args.corpus and args.output.resolve().is_relative_to(args.corpus.resolve().parent):
                raise ValueError('Output must be outside the private input corpus')
            result = load_affine_corpus(args.corpus) if args.corpus else self_audit()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            print('Wrote model tests and coverage, not recovered FPGA logic.')
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as error:
        p.exit(2, f'Affine probe failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
