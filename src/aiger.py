# Aiger parser
from z3 import *
from circuit import *

def _decode_varlen(buf, pos):
    shift = 0; res = 0
    while True:
        ch = buf[pos]; pos += 1
        res |= (ch & 0x7f) << shift
        if (ch & 0x80) == 0:
            return res, pos
        shift += 7

def parse_aiger(data):
    binary = isinstance(data, (bytes, bytearray)) and data[:3] == b'aig'
    if isinstance(data, (bytes, bytearray)) and not binary:
        data = data.decode('ascii', 'replace')

    if not binary:                                   
        lines = data.strip().split('\n')
        h = lines[0].split()
        assert h[0] == 'aag', f'expected aag header, got {h[0]!r}'
        nums = list(map(int, h[1:]))
        M, I, L, O, A = nums[:5]
        B = nums[5] if len(nums) > 5 else 0
        C = nums[6] if len(nums) > 6 else 0
        if len(nums) > 7 and any(nums[7:]):
            raise ValueError('justice/fairness (liveness) not supported')
        p = 1
        inputs = [int(lines[p + k]) for k in range(I)];           
        p += I
        latches = []
        for k in range(L):
            t = list(map(int, lines[p + k].split()))
            latches.append((t[0], t[1], t[2] if len(t) > 2 else 0))  # reset defaults to 0
        p += L
        outputs = [int(lines[p + k]) for k in range(O)];          
        p += O
        bads    = [int(lines[p + k]) for k in range(B)];          
        p += B
        p += C                                                    
        ands = {}
        for k in range(A):
            lhs, r0, r1 = map(int, lines[p + k].split())
            ands[lhs >> 1] = (r0, r1)
        return dict(M=M, I=I, L=L, O=O, A=A, B=B, C=C, inputs=inputs,
                    latches=latches, outputs=outputs, bads=bads, ands=ands)

    nl = data.index(b'\n')
    nums = list(map(int, data[:nl].split()[1:]))
    M, I, L, O, A = nums[:5]
    B = nums[5] if len(nums) > 5 else 0
    C = nums[6] if len(nums) > 6 else 0
    if len(nums) > 7 and any(nums[7:]):
        raise ValueError('justice/fairness (liveness) not supported')
    inputs = [2 * (k + 1) for k in range(I)]          
    pos = nl + 1
    def read_line():
        nonlocal pos
        e = data.index(b'\n', pos)
        s = data[pos:e].decode(); pos = e + 1
        return s
    latches = []
    for k in range(L):
        t = list(map(int, read_line().split()))
        own = 2 * (I + 1 + k)
        latches.append((own, t[0], t[1] if len(t) > 1 else 0))
    outputs = [int(read_line()) for _ in range(O)]
    bads    = [int(read_line()) for _ in range(B)]
    for _ in range(C): read_line()
    ands = {}
    for k in range(A):
        lhs = 2 * (I + L + 1 + k)
        d0, pos = _decode_varlen(data, pos)
        d1, pos = _decode_varlen(data, pos)
        r0 = lhs - d0
        ands[lhs >> 1] = (r0, r0 - d1)
    return dict(M=M, I=I, L=L, O=O, A=A, B=B, C=C, inputs=inputs,
                latches=latches, outputs=outputs, bads=bads, ands=ands)


def aiger_to_circuit(a):
    I, L = a['I'], a['L']
    in_name  = {k + 1:     f'i{k}' for k in range(I)}
    lat_name = {I + 1 + k: f'l{k}' for k in range(L)}
    memo = {}
    def node(var):
        if var in memo: return memo[var]
        if   var in in_name:  e = Bool(in_name[var])
        elif var in lat_name: e = Bool(lat_name[var])
        else:
            r0, r1 = a['ands'][var]
            e = And(lit(r0), lit(r1))
        memo[var] = e
        return e
    def lit(l):
        if l == 0: return BoolVal(False)
        if l == 1: return BoolVal(True)
        e = node(l >> 1)
        return Not(e) if (l & 1) else e

    state  = [lat_name[v] for v in sorted(lat_name)]
    inputs = [in_name[v]  for v in sorted(in_name)]
    nxt, init_terms = {}, []
    for k, (own, nlit, reset) in enumerate(a['latches']):
        name = f'l{k}'
        nxt[name] = lit(nlit)
        if   reset == 0:     init_terms.append(Not(Bool(name)))
        elif reset == 1:     init_terms.append(Bool(name))
        elif reset == own:   pass                              # uninitialized
        else:                init_terms.append(Bool(name) == lit(reset))  # reset function
    init = And(*init_terms) if init_terms else BoolVal(True)
    targets = a['bads'] if a['bads'] else a['outputs']
    prop = And(*[Not(lit(t)) for t in targets]) if targets else BoolVal(True)
    return Circuit(state, inputs, nxt, init, prop)
