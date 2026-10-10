"""Isolated original ADDI/SUBI audit with synthetic CPU state, not arcade traces.

Only a hash-verified private original image is accepted. Generated game code
exists temporarily; the output contains metadata rather than instructions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

from .i960 import decode
from .i960_cpp import emit_cpp
from .serial_contract import HOTDO_SHA256

# pc, mnemonic, src1 register/literal field, src2, destination, src1 literal
SITES = ((0x1034, 'subi', 18, 15, 15, False),
         (0x103c, 'addi', 18, 12, 12, False),
         (0x1060, 'addi', 1, 19, 19, True))


def vectors() -> list[tuple[int, ...]]:
    """Use unbounded Python integers as an independent arithmetic oracle."""
    edges = (0, 1, 2, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff)
    rng = random.Random(0x960591593)
    result = []
    for pc, op, aidx, bidx, dst, literal in SITES:
        pairs = ([(1, b) for b in edges] + [(1, rng.getrandbits(32)) for _ in range(512)]
                 if literal else [(a, b) for a in edges for b in edges]
                 + [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(512)])
        for a, b in pairs:
            sa, sb = (a if a < 2**31 else a - 2**32), (b if b < 2**31 else b - 2**32)
            value = sb - sa if op == 'subi' else sb + sa
            result.append((pc, aidx, bidx, dst, int(literal), a, b,
                           value & 0xffffffff, int(not -2**31 <= value < 2**31)))
    return result


def render_harness(rows: list[tuple[int, ...]]) -> str:
    if not rows:
        raise ValueError('No independent expected values')
    values = ',\n'.join('{' + ','.join(str(v)+'u' for v in row) + '}' for row in rows)
    return r'''
#include <iostream>
using namespace arcaderecomp_generated;
struct Case {std::uint32_t pc,src1,src2,dst,literal,a,b,result,overflow;};
static const Case cases[]={''' + values + r'''};
int main() {
    unsigned checked=0; Bus bus{};
    for(const auto& c:cases) for(unsigned state=0;state<16;++state)
    for(unsigned ck=0;ck<2;++ck) {
        CPU cpu{};cpu.ip=c.pc;
        for(unsigned r=0;r<32;++r)cpu.r[r]=0xa5000000u+r;
        if(!c.literal)cpu.r[c.src1]=c.a;
        cpu.r[c.src2]=c.b;
        std::uint32_t before[32]{};
        for(unsigned r=0;r<32;++r)before[r]=cpu.r[r];
        cpu.integer_overflow_mask_defined=state&1;cpu.integer_overflow_mask=state&2;
        cpu.integer_overflow_flag_defined=state&4;cpu.integer_overflow_flag=state&8;
        cpu.cc=5;cpu.cc_defined=ck;
        const bool unknown=c.overflow && !(state&1);
        const bool trap=c.overflow && (state&1) && !(state&2);
        const bool masked=c.overflow && (state&1) && (state&2);
        const bool ok=step(cpu,bus);
        if(ok!=(!unknown&&!trap))return 1;
        for(unsigned r=0;r<32;++r)
            if(cpu.r[r]!=(r==c.dst&&!unknown?c.result:before[r]))return 2;
        if(cpu.cc!=5||cpu.cc_defined!=bool(ck))return 3;
        if(cpu.integer_overflow_flag!=(masked?true:bool(state&8))||
           cpu.integer_overflow_flag_defined!=(masked?true:bool(state&4)))return 4;
        if(cpu.integer_overflow_mask!=bool(state&2)||
           cpu.integer_overflow_mask_defined!=bool(state&1))return 5;
        if(cpu.ip!=c.pc+(ok?4:0)||cpu.pending_integer_overflow.pending!=trap)return 6;
        if(unknown&&(cpu.stop_code!=StopCode::undefined_integer_controls||cpu.stop_ip!=c.pc))return 7;
        if(trap) {
            if(cpu.stop_code!=StopCode::integer_overflow_pending||cpu.stop_ip!=c.pc||
               cpu.pending_integer_overflow.instruction_ip!=c.pc||
               cpu.pending_integer_overflow.resume_ip!=c.pc+4)return 8;
            if(step(cpu,bus)||cpu.r[c.dst]!=c.result||cpu.ip!=c.pc)return 9;
        }
        ++checked;
    }
    std::cout<<"{\"checks\":"<<checked
      <<",\"synthetic_cpu_state\":true,\"hardware_verified\":false}\n";
}
'''


def parse_result(text: str, expected: int) -> dict:
    if not isinstance(text, str) or len(text) > 1024:
        raise ValueError('Invalid native report length')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate native report field')
            obj[key] = value
        return obj
    obj = json.loads(text, object_pairs_hook=unique)
    if type(obj) is not dict or set(obj) != {'checks', 'synthetic_cpu_state', 'hardware_verified'}:
        raise ValueError('Invalid native report schema')
    if type(obj['checks']) is not int or obj['checks'] != expected:
        raise ValueError('Incomplete native comparisons')
    if obj['synthetic_cpu_state'] is not True or obj['hardware_verified'] is not False:
        raise ValueError('Invalid evidence classification')
    return obj


def run_audit(path: Path, compilers: tuple[str, ...] = ('g++', 'clang++')) -> dict:
    if path.stat().st_size != 0x200000:
        raise ValueError('Expected a mapped 2-MiB original image')
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original CPU image hash mismatch')
    if not compilers or len(set(compilers)) != len(compilers):
        raise ValueError('Select distinct compilers')
    for pc, op, a, b, dst, literal in SITES:
        ins = decode(image, pc)
        if not ins.supported or ins.mnemonic != op or ins.size != 4 or (
            ins.word & 31, (ins.word >> 14) & 31, (ins.word >> 19) & 31,
            bool(ins.word & 0x800), bool(ins.word & 0x1000)) != (a, b, dst, literal, False):
            raise ValueError('Original arithmetic-site identity changed')
    code, graph = emit_cpp(image, 0x5f0, 16384, additional_entries=(0x6b0,))
    if graph.limit_reached or any(site[0] in graph.unsupported for site in SITES):
        raise ValueError('Arithmetic code generation incomplete')
    rows = vectors(); expected = len(rows)*32
    root = Path(__file__).resolve().parents[1]
    reports = []
    with tempfile.TemporaryDirectory(prefix='arcade-private-integer-') as folder:
        work = Path(folder); source = work/'probe.cpp'
        source.write_text(code + '\n' + render_harness(rows), encoding='utf-8')
        for index, name in enumerate(compilers):
            compiler = shutil.which(name)
            if not compiler:
                raise ValueError('Compiler missing: ' + name)
            exe = work/('probe'+str(index)+('.exe' if os.name == 'nt' else ''))
            build = subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(root/'runtime'),
                str(source), '-o', str(exe)], capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise ValueError('Native compilation failed: '+build.stderr[-3000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            if run.returncode:
                raise ValueError(f'Native comparison failed ({run.returncode}): '+run.stderr[-3000:])
            reports.append(parse_result(run.stdout, expected))
    if any(report != reports[0] for report in reports):
        raise ValueError('Compiler reports differ')
    return {'schema_version': 1, 'image_sha256': HOTDO_SHA256,
        'evidence': 'isolated_original_opcodes_with_synthetic_cpu_state',
        'sites': [{'pc': hex(s[0]), 'mnemonic': s[1]} for s in SITES],
        'input_vectors': len(rows), 'comparisons_per_compiler': expected,
        'compilers': list(compilers), 'reports_identical': True,
        'sanitizer': 'undefined', 'native_result': reports[0],
        'static_candidates': graph.discovered, 'native_emitting_sites': graph.translated,
        'unsupported_sites': [hex(pc) for pc in graph.unsupported],
        'fault_handler_executed': False, 'arcade_hardware_verified': False,
        'model2c_complete': False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cxx', action='append')
    a = p.parse_args()
    try:
        if a.image.resolve() == a.output.resolve() or (a.output.exists() and a.output.samefile(a.image)):
            raise ValueError('Output must not overwrite input image')
        report = run_audit(a.image, tuple(a.cxx) if a.cxx else ('g++', 'clang++'))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print('Original arithmetic sites checked with synthetic CPU state; not hardware validation.')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        p.exit(2, f'Signed arithmetic audit failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
