"""Synthetic controls for FPGA hypotheses; no Sega or reference-design bytes."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from arcaderecomp.flex8000_lut_probe import (HOLDOUTS, TABLES, ahdl, correlate,
    load_corpus, npn_orbit, probe_plan, scan_regular_layout, truth_table, vector)
from arcaderecomp.flex8000_sram import PACKED_BYTES,TOTAL_BITS


def corpus(width=512, duplicate=False, nuisance=False):
    # Sixteen scattered, mixed-polarity bits; not an assumed hardware layout.
    rng=random.Random(8282)
    positions=rng.sample(range(16,width-16),16)
    inversions=[i%3==0 for i in range(16)]
    spare=next(i for i in range(width) if i not in positions)
    def packed(truth,training=False):
        value=0
        for i,(p,inv) in enumerate(zip(positions,inversions)):
            value |= (((truth>>i)&1)^inv)<<p
        if duplicate:
            value |= (truth&1)<<spare
        elif nuisance and training:
            value |= (truth&1)<<spare
        return value.to_bytes((width+7)//8,'little')
    train=[packed(1<<i,True) for i in range(16)]
    held=[(t,packed(t)) for t in HOLDOUTS]
    return train,train[0],held,positions,inversions


def sof(packed,device=b'EPF8282ALC84-2\0'):
    body=b'\0'*6+struct.pack('<I',TOTAL_BITS)+b'\1\0'+packed
    packets=[(2,device),(17,body)]
    return b'SOF\0'+struct.pack('<II',0,len(packets))+b''.join(struct.pack('<HI',k,len(v))+v for k,v in packets)


class TruthClassTests(unittest.TestCase):
    def test_truth_table_order_and_known_orbits(self):
        self.assertEqual(truth_table(lambda a,b,c,d:a),0xaaaa)
        self.assertEqual(truth_table(lambda a,b,c,d:a and b and c and d),0x8000)
        self.assertEqual([len(npn_orbit(t)) for t in TABLES],[192,32,48,8,2])

    def test_orbit_matches_independent_assignment_permutation(self):
        original=0xB249
        # Construct independent input transformation on all assignment tuples.
        bits=list(itertools.product((0,1),repeat=4))
        transformed=0
        for a in bits:
            src=(a[2]^1,a[0],a[3]^1,a[1])
            x=sum(b<<i for i,b in enumerate(a))
            y=sum(b<<i for i,b in enumerate(src))
            transformed |= (((original>>y)&1)^1)<<x
        self.assertIn(transformed,npn_orbit(original))
        self.assertNotIn(0,npn_orbit(original))

    def test_regular_layout_scan_detects_inserted_equation_classes(self):
        sequence=[TABLES[i] for i in (0,1,2,3,3,4,2,3)]
        raw=0
        for i,t in enumerate(sequence):
            raw |= t<<(32+24*i)
        result=scan_regular_layout(raw.to_bytes(32,'little'),256,(1,),32)
        examples=result['results'][0]['examples']
        self.assertIn({'first_lut_bit':32,'cell_stride':24},examples)
        self.assertFalse(result['logic_decoded'])

    def test_uniform_vector_does_not_become_a_lut_layout(self):
        for raw in (b'\0'*32,b'\xff'*32):
            r=scan_regular_layout(raw,256,(1,2),32)
            self.assertTrue(all(x['full_eight_cell_candidates']==0 for x in r['results']))

    def test_bit_numeric_and_scan_bounds_fail_closed(self):
        for value in (True,-1,65536):
            with self.assertRaises(ValueError):npn_orbit(value)
        for strides in ((),(1,1),(0,), (213,)):
            with self.assertRaises(ValueError):scan_regular_layout(b'\0'*32,256,strides)
        with self.assertRaises(ValueError):vector(b'\xff'*3,17)
        with self.assertRaises(ValueError):scan_regular_layout(b'\0'*32,256,(1,),513)


class DifferentialMappingTests(unittest.TestCase):
    def test_scattered_inverted_bits_recovered_in_synthetic_corpus(self):
        train,repeat,held,positions,inversions=corpus()
        result=correlate(train,repeat,held,512)
        self.assertEqual(result['unique_truth_bits'],16)
        for bit,row in enumerate(result['bits']):
            self.assertEqual(row['candidates'],[{'configuration_bit':positions[bit],
                                               'inverted':inversions[bit]}])
        self.assertFalse(result['logic_netlist_recovered'])
        self.assertFalse(result['physical_routing_verified'])

    def test_holdouts_remove_training_only_nuisance_correlations(self):
        train,repeat,held,_,_=corpus(nuisance=True)
        r=correlate(train,repeat,held,512)
        self.assertEqual(r['bits'][0]['training_candidates'],2)
        self.assertEqual(r['bits'][0]['heldout_candidates'],1)

    def test_duplicates_surviving_holdouts_remain_ambiguous(self):
        train,repeat,held,_,_=corpus(duplicate=True)
        r=correlate(train,repeat,held,512)
        self.assertEqual(r['unique_truth_bits'],15)
        self.assertEqual(r['bits'][0]['status'],'ambiguous')
        self.assertEqual(len(r['bits'][0]['candidates']),2)

    def test_bad_holdout_and_nondeterministic_repeat_rejected(self):
        train,repeat,held,_,_=corpus()
        bad=(int.from_bytes(repeat,'little')^1).to_bytes(64,'little')
        with self.assertRaisesRegex(ValueError,'Repeated'):correlate(train,bad,held,512)
        with self.assertRaises(ValueError):correlate(train[:-1],repeat,held,512)
        with self.assertRaises(ValueError):correlate(train,repeat,held[:3],512)
        for wrong in ([(1,held[0][1])]+held[1:],held[:4]+held[:2]):
            with self.assertRaises(ValueError):correlate(train,repeat,wrong,512)

    def test_mutated_holdout_removes_inconsistent_truth_bit(self):
        train,repeat,held,positions,_=corpus()
        t,v=held[0]
        held[0]=(t,(int.from_bytes(v,'little')^(1<<positions[3])).to_bytes(64,'little'))
        result=correlate(train,repeat,held,512)
        self.assertEqual(result['unique_truth_bits'],15)
        self.assertEqual(result['bits'][3]['status'],'not_identified')


class ProbePlanAndCorpusTests(unittest.TestCase):
    def test_original_ahdl_matches_all_requested_truth_values(self):
        plan=probe_plan()
        self.assertEqual(len(plan['cases']),23)
        self.assertFalse(plan['compiled'])
        self.assertEqual(plan['cases'][0]['truth'],plan['cases'][16]['truth'])
        for case in plan['cases']:
            text=ahdl(case['truth'])
            terms=re.findall(r'\((!?a\[0\] & !?a\[1\] & !?a\[2\] & !?a\[3\])\)',text)
            reconstructed=0
            for term in terms:
                assignment=term.split(' & ')
                n=sum(int(not v.startswith('!'))<<i for i,v in enumerate(assignment))
                reconstructed|=1<<n
            self.assertEqual(reconstructed,case['truth'])

    def manifest(self,root):
        train,repeat,held,_,_=corpus(TOTAL_BITS)
        data=[('train',1<<i,v) for i,v in enumerate(train)]+[('repeat',1,repeat)]
        data += [('holdout',t,v) for t,v in held]
        entries=[]
        for i,(role,t,p) in enumerate(data):
            raw=sof(p);path=root/f'case{i}.sof';path.write_bytes(raw)
            entries.append({'role':role,'truth':t,'sof':path.name,'sha256':hashlib.sha256(raw).hexdigest()})
        doc={'schema_version':1,'cases':entries}
        m=root/'corpus.json';m.write_text(json.dumps(doc))
        return m,doc

    def test_manifest_reads_real_sof_shape_with_synthetic_data(self):
        with tempfile.TemporaryDirectory() as d:
            manifest,_=self.manifest(Path(d))
            r=load_corpus(manifest)
            self.assertEqual(r['unique_truth_bits'],16)
            self.assertEqual(r['device'],'EPF8282ALC84-2')
            self.assertFalse(r['compiler_executed_by_this_tool'])

    def test_manifest_identity_mixed_target_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,doc=self.manifest(root)
            for field,value in [('sha256','0'*64),('sof','../escape.sof'),('truth',True)]:
                bad=copy.deepcopy(doc);bad['cases'][0][field]=value
                manifest.write_text(json.dumps(bad))
                with self.assertRaises((ValueError,OSError)):load_corpus(manifest)
            manifest.write_text(json.dumps(doc))
            file=root/doc['cases'][0]['sof']
            replacement=sof(bytes(PACKED_BYTES),b'EPF8282ATC100-2\0')
            file.write_bytes(replacement)
            doc['cases'][0]['sha256']=hashlib.sha256(replacement).hexdigest()
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'mixes'):load_corpus(manifest)

    def test_cli_plan_never_overwrites_or_claims_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            plan=Path(d)/'plan'
            command=[sys.executable,'-m','arcaderecomp.flex8000_lut_probe','--plan',str(plan)]
            run=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('uncompiled',run.stdout)
            self.assertEqual(len(list(plan.rglob('*.tdf'))),23)
            again=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertEqual(again.returncode,2)

    def test_cli_report_cannot_overwrite_any_corpus_input(self):
        with tempfile.TemporaryDirectory() as d:
            manifest,_=self.manifest(Path(d))
            original=manifest.read_bytes()
            run=subprocess.run([sys.executable,'-m','arcaderecomp.flex8000_lut_probe','--corpus',str(manifest),
                '--output',str(manifest)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertEqual(manifest.read_bytes(),original)

if __name__=='__main__':unittest.main()
