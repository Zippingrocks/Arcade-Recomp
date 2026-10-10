"""Independent synthetic controls, not discoveries in the HOTD1 FPGA."""
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest

from arcaderecomp.flex8000_affine_probe import (
    ADDED_HOLDOUTS, STRONG_HOLDOUTS, affine_models, load_affine_corpus,
    sample_coverage, self_audit, stronger_plan, write_plan)
from arcaderecomp.flex8000_lut_probe import (
    HOLDOUTS, ahdl, correlate, load_corpus, probe_plan, read_corpus)
from arcaderecomp.flex8000_sram import TOTAL_BITS
from test_flex8000_lut_probe import sof


def make_data(masks, constants, width=64, truths=STRONG_HOLDOUTS):
    def packed(truth):
        # Independent coefficient-array dot product, not production bit_count.
        value = 0
        for position, (mask, constant) in enumerate(zip(masks, constants)):
            bit = constant
            for i in range(16):
                if mask & (1 << i) and truth & (1 << i):
                    bit ^= 1
            value |= bit << position
        return value.to_bytes((width + 7) // 8, 'little')
    train = [packed(1 << n) for n in range(16)]
    return train, train[0], [(t, packed(t)) for t in truths], packed


class CoverageTests(unittest.TestCase):
    def test_old_plan_has_22_blind_pairs_new_plan_has_none(self):
        old = sample_coverage([c['truth'] for c in probe_plan()['cases']])
        new = stronger_plan()
        self.assertEqual(old['fully_observed_pairs'], 98)
        self.assertEqual(len(old['incomplete_pairs']), 22)
        self.assertIn({'truth_bits': [0, 1], 'missing_assignments': [3]}, old['incomplete_pairs'])
        self.assertEqual(new['source_count'], 26)
        self.assertEqual(new['coverage']['fully_observed_pairs'], 120)
        self.assertEqual(new['coverage']['incomplete_pairs'], [])
        self.assertFalse(new['coverage']['nonlinear_behaviors_excluded'])
        self.assertEqual(len(probe_plan()['cases']), 23)  # old experiment unchanged

    def test_all_pair_assignments_with_independent_tuple_oracle(self):
        tables = [c['truth'] for c in stronger_plan()['cases']]
        for a, b in itertools.combinations(range(16), 2):
            pairs = {((t // (2 ** a)) % 2, (t // (2 ** b)) % 2) for t in tables}
            self.assertEqual(pairs, {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.assertEqual(sample_coverage([1 << n for n in range(16)])['affine_design_rank'], 16)
        self.assertEqual(sample_coverage([1 << n for n in range(16)] + [0])['affine_design_rank'], 17)

    def test_new_probe_functions_retain_four_input_dependencies(self):
        for truth in ADDED_HOLDOUTS:
            for input_bit in range(4):
                self.assertTrue(any(((truth >> n) & 1) != ((truth >> (n ^ (1 << input_bit))) & 1)
                                    for n in range(16)))
        plan = stronger_plan()
        self.assertFalse(plan['compiled'])
        self.assertFalse(plan['placement_or_routing_guaranteed'])
        for case in plan['cases']:
            terms = re.findall(r'\((!?a\[0\] & !?a\[1\] & !?a\[2\] & !?a\[3\])\)', ahdl(case['truth']))
            reconstructed = sum(1 << sum(int(not token.startswith('!')) << j
                                        for j, token in enumerate(term.split(' & '))) for term in terms)
            self.assertEqual(reconstructed, case['truth'])

    def test_coverage_rejects_unbounded_or_invalid_values(self):
        for tables in ([], [1] * 65, [True], [-1], [65536], (1, 2)):
            with self.assertRaises(ValueError):
                sample_coverage(tables)


class AffineModelTests(unittest.TestCase):
    def test_scattered_encoded_truth_combinations_and_inversion(self):
        rng = random.Random(82820)
        masks = [0, 0, 1, 0x8000, 3, 0x5555, 0xffff] + [rng.randrange(65536) for _ in range(57)]
        constants = [0, 1] + [rng.randrange(2) for _ in range(62)]
        train, repeat, holdouts, _ = make_data(masks, constants)
        r = affine_models(train, repeat, holdouts, 64, 64)
        self.assertEqual(r['counts']['ambiguous_intercept'], 0)
        self.assertEqual(r['counts']['no_affine_model_on_samples'], 0)
        self.assertEqual(sum(r['unique_model_term_count_histogram']), 64)
        for row in r['examples']:
            p = row['configuration_bit']
            self.assertEqual(row['models'], [{'truth_mask': masks[p], 'xor_constant': constants[p]}])
        self.assertFalse(r['physical_lut_identified'])
        self.assertFalse(r['hardware_validation'])

    def test_all_65536_truth_values_against_known_synthetic_affine_functions(self):
        masks = [1, 3, 0xa531, 0xffff]
        constants = [0, 1, 1, 0]
        tr, rep, held, _ = make_data(masks, constants, 16)
        fitted = affine_models(tr, rep, held, 16)['examples']
        self.assertEqual(len(fitted), 4)
        for truth in range(65536):
            for row in fitted:
                p, model = row['configuration_bit'], row['models'][0]
                predicted = (truth & model['truth_mask']).bit_count() % 2 ^ model['xor_constant']
                # Independent list/parity oracle with the original known coefficients.
                actual = (sum((truth >> bit) & 1 for bit in range(16) if masks[p] >> bit & 1) + constants[p]) % 2
                self.assertEqual(predicted, actual)

    def test_odd_weight_holdouts_do_not_identify_intercept(self):
        odd = (7, 0x13, 0x25, 0x8003)
        tr, rep, held, _ = make_data([0x315], [1], 16, odd)
        r = affine_models(tr, rep, held, 16)
        self.assertEqual(r['coverage']['affine_design_rank'], 16)
        self.assertEqual(r['counts']['ambiguous_intercept'], 16)
        self.assertEqual(len(r['examples'][0]['models']), 2)

    def test_corrupted_repeat_and_invalid_holdouts_fail(self):
        tr, rep, held, _ = make_data([3], [0])
        for repeat, trials in (((int.from_bytes(rep, 'little') ^ 1).to_bytes(len(rep), 'little'), held),
                               (rep, held[:3]), (rep, held + [held[0]]),
                               (rep, [(1, held[0][1])] + held[1:])):
            with self.assertRaises(ValueError):
                affine_models(tr, repeat, trials, 64)
        for examples in (-1, 257, True):
            with self.assertRaises(ValueError):
                affine_models(tr, rep, held, 64, examples)

    def test_old_false_positive_is_reproduced_and_new_holdouts_reject_it(self):
        r = self_audit()
        old = r['old_direct_mapper_result_for_truth_bit_2']
        new = r['extended_mapper_result_for_truth_bit_2']
        self.assertEqual(old['status'], 'unique_in_corpus')
        self.assertEqual(old['candidates'], [{'configuration_bit': 37, 'inverted': False}])
        self.assertEqual(new['status'], 'not_identified')
        self.assertEqual(r['extended_affine_result_counts']['no_affine_model_on_samples'], 1)
        self.assertFalse(r['compiled_real_corpus_used'])

    def test_pair_coverage_does_not_claim_to_exclude_all_nonlinear_alternatives(self):
        # A function can differ at an unobserved whole truth table, even with
        # complete pair coverage. A new holdout at that table exposes it.
        def packed(t):
            bit = ((t >> 2) & 1) ^ int(t == 0x1234)
            return (bit << 7).to_bytes(8, 'little')
        tr = [packed(1 << n) for n in range(16)]
        held = [(t, packed(t)) for t in STRONG_HOLDOUTS]
        old = affine_models(tr, tr[0], held, 64)
        self.assertEqual(old['counts']['one_truth_bit_model'], 1)
        self.assertFalse(old['coverage']['nonlinear_behaviors_excluded'])
        new = affine_models(tr, tr[0], held + [(0x1234, packed(0x1234))], 64)
        self.assertEqual(new['counts']['no_affine_model_on_samples'], 1)

    def test_result_identity_is_deterministic_and_example_output_is_bounded(self):
        tr, rep, held, _ = make_data([3] * 64, [1] * 64)
        a = affine_models(tr, rep, held, 64, 2)
        b = affine_models(tr, rep, held[::-1], 64, 64)
        self.assertTrue(a['examples_truncated'])
        self.assertEqual(len(a['examples']), 2)
        self.assertEqual(a['all_candidate_models_sha256'], b['all_candidate_models_sha256'])
        empty = affine_models(tr, rep, held, 64, 0)
        self.assertEqual(empty['examples'], [])


class CorpusAndCLITests(unittest.TestCase):
    def manifest(self, root):
        tr, rep, held, _ = make_data([1 << n for n in range(16)] + [0x93], [0] * 17, TOTAL_BITS)
        values = [('train', 1 << n, v) for n, v in enumerate(tr)] + [('repeat', 1, rep)]
        values += [('holdout', t, v) for t, v in held]
        cases = []
        for n, (role, truth, data) in enumerate(values):
            raw = sof(data)
            name = f'{n}.sof'
            (root / name).write_bytes(raw)
            cases.append({'role': role, 'truth': truth, 'sof': name, 'sha256': hashlib.sha256(raw).hexdigest()})
        path = root / 'manifest.json'
        path.write_text(json.dumps({'schema_version': 1, 'cases': cases}))
        return path

    def test_shared_identity_reader_preserves_direct_mapper(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.manifest(Path(d))
            inputs = read_corpus(path)
            direct = load_corpus(path)
            self.assertEqual(direct['unique_truth_bits'], 16)
            new = load_affine_corpus(path)
            self.assertEqual(new['counts']['one_truth_bit_model'], 16)
            self.assertEqual(new['counts']['multiple_truth_bit_model'], 1)
            self.assertEqual(new['source_hashes'], inputs['identities'])
            self.assertTrue(new['coverage']['all_pair_assignments_observed'])
            self.assertFalse(new['compiler_executed_by_this_tool'])

    def test_tampered_sof_is_rejected_by_new_corpus_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = self.manifest(root)
            (root / '0.sof').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'identity'):
                load_affine_corpus(path)

    def test_plan_writes_26_uncompiled_sources_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'probes'
            write_plan(p)
            self.assertEqual(len(list(p.rglob('*.tdf'))), 26)
            doc = json.loads((p / 'plan.json').read_text())
            self.assertFalse(doc['compiled'])
            self.assertTrue(doc['coverage']['all_pair_assignments_observed'])
            with self.assertRaises(ValueError):
                write_plan(p)
            self.assertEqual((p / 'minterm_00/lut_probe.tdf').read_bytes(),
                             (p / 'repeat_00/lut_probe.tdf').read_bytes())

    def test_cli_self_audit_and_output_over_input_guard(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / 'audit.json'
            proc = subprocess.run([sys.executable, '-m', 'arcaderecomp.flex8000_affine_probe',
                                   '--self-audit', '--output', str(out)], capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(out.read_text())['schema_version'], 1)
            path = self.manifest(root)
            before = path.read_bytes()
            bad = subprocess.run([sys.executable, '-m', 'arcaderecomp.flex8000_affine_probe',
                                  '--corpus', str(path), '--output', str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
