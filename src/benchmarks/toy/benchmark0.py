# Benchmarks in Aiger

# aag M I L O A
# M - number of literals (starts at 0).
# I - inputs
# L - latches
# O - outputs
# A - # And gates

# (inputs, latches, gates)
# literal = 2 * variable + sign

from aiger import *
from circuit import *
from ic3 import *

BENCHMARKS = {}


BENCHMARKS['cnt1'] = ("""\
aag 1 0 1 0 0 1
2 3
2
""", 'UNSAFE')   # 1-bit toggle; bad when bit==1  -> reachable

BENCHMARKS['notcnt1'] = ("""\
aag 1 0 1 0 0 1
2 3
3
""", 'UNSAFE')   # bad when bit==0  -> true at reset

BENCHMARKS['cnt1e'] = ("""\
aag 5 1 1 0 3 1
2
4 10
4
6 5 3
8 4 2
10 9 7
""", 'UNSAFE')   # enable can flip the bit to 1

BENCHMARKS['notcnt1e'] = ("""\
aag 5 1 1 0 3 1
2
4 10
5
6 5 3
8 4 2
10 9 7
""", 'UNSAFE')

BENCHMARKS['stuck0'] = ("""\
aag 1 0 1 0 0 1
2 2 0
2
""", 'SAFE')

BENCHMARKS['stuck1'] = ("""\
aag 1 0 1 0 0 1
2 2 1
3
""", 'SAFE')

BENCHMARKS['cnt2_reaches3'] = ("""\
aag 6 0 2 0 4 1
2 3
4 11
12
6 4 3
8 5 2
10 9 7
12 4 2
""", 'UNSAFE')

BENCHMARKS['cnt2_mod3'] = ("""\
aag 5 0 2 0 3 1
2 6
4 8
10
6 5 3
8 5 2
10 4 2
""", 'SAFE')

BENCHMARKS['cnt2_saturate'] = ("""\
aag 4 0 2 0 2 1
2 6
4 7
8
6 5 3
8 4 2
""", 'SAFE')

BENCHMARKS['lockstep_equal'] = ("""\
aag 5 0 2 0 3 1
2 3
4 5
11
6 5 2
8 4 3
10 9 7
""", 'SAFE')

BENCHMARKS['free_input'] = ("""\
aag 2 1 1 0 0 1
2
4 2
4
""", 'UNSAFE')

BENCHMARKS['xor_swap'] = ("""\
aag 5 0 2 0 3 1
2 4
4 2 1
11
6 4 2
8 5 3
10 9 7
""", 'SAFE')


import io, contextlib

print(f"{'benchmark':16s} {'result':8s} {'expected':8s}  match")
print('-' * 46)
for name, (text, expected) in BENCHMARKS.items():
    ckt = aiger_to_circuit(parse_aiger(text))
    with contextlib.redirect_stdout(io.StringIO()):
        inv = PDR(ckt, use_ternary=True)
    result = 'UNSAFE' if inv is False else ('SAFE' if inv is not None else 'UNKNOWN')
    print(f"{name:16s} {result:8s} {expected:8s}  {'OK' if result == expected else 'MISMATCH'}")
