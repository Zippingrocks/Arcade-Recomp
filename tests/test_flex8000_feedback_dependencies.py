"""A syntactic feedback loop can cancel in the actual Boolean function."""
import unittest
from arcaderecomp.flex8000_feedback_audit import Cell, Network, feedback_sizes, relation
from arcaderecomp.flex8000_fit_constraints import parse_expression

class CanceledDependencyTests(unittest.TestCase):
    def test_syntactic_feedback_that_cancels_is_not_a_functional_cycle(self):
        cell=Cell('a',False,('a',None,None,None),parse_expression('a # !a'))
        net=Network((),(cell,))
        self.assertEqual(feedback_sizes(net),[])
        result=relation(net,(65535,))
        self.assertTrue(result['all_fixed_points_match'])
        self.assertEqual(result['reference_fixed_point_count_histogram'],{'1':1})

if __name__=='__main__':unittest.main()
