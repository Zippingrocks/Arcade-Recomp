"""Artificial Boolean-network oracles, not compiler or Sega design payloads."""
import json
import unittest
from unittest.mock import patch

from arcaderecomp.flex8000_feedback_audit import (
    Cell, Network, feedback_sizes, relation, report_network, audit_pinned_inputs)
from arcaderecomp.flex8000_fit_constraints import parse_expression, transform
from arcaderecomp.flex8000_fit_slots import PINNED
from arcaderecomp.flex8000_compare import git_blob_sha1
from arcaderecomp.flex8000_lut_tiles import CANDIDATE, tile_offsets
from arcaderecomp.flex8000_sram import PACKED_BYTES
from test_flex8000_fit_slots import report, fit, DEVICE
from test_flex8000_sram import rcs, sof


def cell(name, expr, slots=(), registered=False):
    return Cell(name, registered, tuple(slots)+(None,)*(4-len(slots)), parse_expression(expr))


def raw(function):
    # Independent tuple-coordinate oracle, not the production transform.
    return sum(int(function(*[1-((i//(2**j))%2) for j in range(4)])) << i for i in range(16))


class FeedbackRelationTests(unittest.TestCase):
    def test_feedforward_network_has_unique_solution_per_input(self):
        net = Network(('a','b'), (cell('n1','a & b',('a','b')), cell('n2','!n1',('n1',))))
        result = relation(net, (raw(lambda a,b,c,d:a&b), raw(lambda a,b,c,d:1-a)))
        self.assertEqual(result['assignments_exhaustively_tested'],16)
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'1':4})
        self.assertEqual(result['combinational_feedback_component_sizes'],[])
        self.assertTrue(result['all_cell_bits_match'] and result['all_fixed_points_match'])

    def test_even_inverter_loop_keeps_both_solutions(self):
        net = Network((), (cell('a','!b',('b',)), cell('b','!a',('a',))))
        result = relation(net, (raw(lambda a,b,c,d:1-a),)*2)
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'2':1})
        self.assertEqual(result['combinational_feedback_component_sizes'],[2])
        self.assertEqual(result['ambiguous_reference_boundaries'],1)
        self.assertFalse(result['sequential_semantics_verified'])

    def test_odd_inverter_loop_reports_no_boolean_solution_not_oscillation(self):
        net = Network((), (cell('a','!a',('a',)),))
        result = relation(net, (raw(lambda a,b,c,d:1-a),))
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'0':1})
        self.assertEqual(result['empty_reference_boundaries'],1)
        self.assertNotIn('oscillates',result)
        self.assertTrue(result['all_fixed_points_match'])

    def test_register_output_is_a_cut_not_a_clocked_next_state_guess(self):
        net = Network((), (cell('q','!x',('x',),True), cell('x','q',('q',))))
        result = relation(net, (raw(lambda a,b,c,d:1-a),raw(lambda a,b,c,d:a)),True)
        self.assertEqual(result['combinational_feedback_component_sizes'],[])
        self.assertEqual(result['boundary_cases'],2)
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'1':2})
        self.assertGreaterEqual(result['single_bit_mutations']['invisible_to_register_cut_relation'],16)

    def test_normalized_aliases_match_direct_boolean_oracle(self):
        net = Network(('in',), (cell('a','in',('in',)), cell('b','!a',('a',))),frozenset({'a'}))
        result = relation(net, (raw(lambda a,b,c,d:a),)*2)
        self.assertTrue(result['all_cell_bits_match'])
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'1':2})

    def test_changed_candidate_can_change_fixed_points(self):
        net = Network(('in',), (cell('a','in',('in',)),))
        result = relation(net, (raw(lambda a,b,c,d:1-a),))
        self.assertFalse(result['all_cell_bits_match'])
        self.assertEqual(result['boundary_cases_with_different_solution_sets'],2)
        with self.assertRaisesRegex(ValueError,'baseline'):
            relation(net,(0,),True)

    def test_unused_slot_mutation_invisible_to_relation_but_not_exact_table_gate(self):
        net = Network(('in',), (cell('a','in',('in',)),))
        correct=raw(lambda a,b,c,d:a)
        result=relation(net,(correct^1,))
        self.assertTrue(result['all_fixed_points_match'])
        self.assertFalse(result['all_cell_bits_match'])
        self.assertEqual(result['exact_cell_bit_matches'],15)

    def test_full_table_mutation_sensitivity_independent_of_circuit_stability(self):
        # A self-buffer admits either state. Only the two visited LUT positions
        # affect the relation; other 14 positions require per-cell checking.
        net=Network((),(cell('a','a',('a',)),))
        result=relation(net,(raw(lambda a,b,c,d:a),),True)
        self.assertEqual(result['single_bit_mutations']['tested'],16)
        self.assertEqual(result['single_bit_mutations']['detected_by_register_cut_relation'],2)
        self.assertEqual(result['single_bit_mutations']['invisible_to_register_cut_relation'],14)

    def test_sccs_respect_data_dependencies_not_all_present_slots(self):
        net=Network((),(cell('a','VCC',('b',)),cell('b','a',('a',))))
        self.assertEqual(feedback_sizes(net),[])
        many=Network((),(cell('a','a',('a',)),cell('b','c',('c',)),cell('c','b',('b',))))
        self.assertEqual(feedback_sizes(many),[1,2])

    def test_malformed_and_unbounded_networks_rejected(self):
        valid=cell('a','VCC')
        invalid=[Network((),()),Network((),(valid,)*9),Network(('a',),(valid,)),
                 Network((),(cell('a','x',('x',)),)),Network((),(valid,),frozenset({'bad'})),
                 Network((),(cell('a','a',('a','a')),)),
                 Network((),(cell('a','a'),)),Network(tuple(f'x{i}' for i in range(9)),(valid,))]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):relation(item,(0,)*len(item.cells))
        for tables in [(),(True,),(65536,),(-1,)]:
            with self.assertRaises(ValueError):relation(Network((),(valid,)),tables)


class ReportPipelineTests(unittest.TestCase):
    def test_fitted_parser_maps_register_data_and_preserves_build_guards(self):
        network,tables=report_network(report(),fit(),DEVICE)
        self.assertEqual(len(network.cells),8)
        self.assertEqual(len(network.inputs),5)
        self.assertEqual(sum(c.registered for c in network.cells),1)
        result=relation(network,tuple(transform(t,(0,1,2,3),15,0) for t in tables))
        self.assertTrue(result['all_cell_bits_match'] and result['all_fixed_points_match'])
        with self.assertRaises(ValueError):report_network(report(),fit().replace('04:05:06','04:05:07'),DEVICE)

    def fixture(self):
        _,tables=report_network(report(),fit(),DEVICE)
        raw_tables=tuple(transform(t,(0,1,2,3),15,0) for t in tables)
        data=0
        for i,t in enumerate(raw_tables):
            for j,off in enumerate(tile_offsets(8,177,1)):
                data|=((t>>j)&1)<<(CANDIDATE['first_bit']+i*CANDIDATE['cell_stride']+off)
        files=(rcs(sof(data.to_bytes(PACKED_BYTES,'little'))),rcs(report().encode()),rcs(fit().encode()))
        return files,{n:git_blob_sha1(v) for n,v in zip(PINNED,files)}

    def test_pinned_pipeline_exports_only_counts_and_explicit_limits(self):
        files,pins=self.fixture()
        with patch('arcaderecomp.flex8000_feedback_audit.PINNED',pins): result=audit_pinned_inputs(*files)
        self.assertTrue(result['result']['all_fixed_points_match'])
        self.assertFalse(result['new_independent_design'] or result['runtime_changed'] or result['model2c_complete'])
        for name in ('_LC1_B1','/RESET','expression','packed','truth_table','solution_states'):
            self.assertNotIn(name,json.dumps(result))

    def test_changed_reference_stops_before_parsing(self):
        files,pins=self.fixture()
        with patch('arcaderecomp.flex8000_feedback_audit.PINNED',pins):
            for i in range(3):
                changed=list(files);changed[i]+=b' '
                with self.assertRaisesRegex(ValueError,'identity'):audit_pinned_inputs(*changed)

if __name__=='__main__':unittest.main()
