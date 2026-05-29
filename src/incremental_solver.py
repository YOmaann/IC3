from z3 import *
from utils.utils import *
from circuit import *

class IncrementalSolver:
    def __init__(self, variables, ckt, use_ternary=True):
        self.solver = Solver()
        self.variables = variables
        self.ckt = ckt                       # the circuit, for ternary simulation
        self.use_ternary = use_ternary
        self.stats = {'minterms': 0, 'lits_in': 0, 'lits_out': 0, 'probes': 0}

    def _bind(self):
        return bind(self.variables)

    def _ternary_predecessor(self, pred01, ival, target):
        a = dict(pred01)
        for v in self.ckt.state:
            if a[v] is X:
                continue
            saved = a[v]
            a[v] = X
            self.stats['probes'] += 1
            ns = self.ckt.ternary_step(a, ival)
            if all(ns[w] == (1 if target[w] else 0) for w in target):
                pass                       
            else:
                a[v] = saved               
        return {v: (a[v] == 1) for v in self.ckt.state if a[v] is not X}

    def _ternary_bad(self, bad01):
        a = dict(bad01)
        for v in self.ckt.state:
            if a[v] is X:
                continue
            saved = a[v]
            a[v] = X
            self.stats['probes'] += 1
            if self.ckt.ternary_prop(a) == 0:
                pass                        
            else:
                a[v] = saved
        return {v: (a[v] == 1) for v in self.ckt.state if a[v] is not X}


    def getBadCube(self, frames, P_expr):
        vd, _ = self._bind()
        N = frames.depth()
        self.solver.push()
        self.solver.add(frames.get_R(N, vd))
        self.solver.add(Not(P_expr))
        result = None
        if self.solver.check() == sat:
            result = extract_cube(self.solver.model(), vd, self.variables)
        self.solver.pop()
        if result is not None and self.use_ternary:
            bad01 = {v: (1 if result[v] else 0) for v in self.variables}
            self.stats['minterms'] += 1
            self.stats['lits_in'] += len(result)
            result = self._ternary_bad(bad01)
            self.stats['lits_out'] += len(result)
        return result

    def isInitial(self, cube, init_expr):
        vd, _ = self._bind()
        self.solver.push()
        self.solver.add(init_expr)
        self.solver.add(cube_to_expr(cube, vd))
        res = self.solver.check() == sat
        self.solver.pop()
        return res

    def solveRelative(self, cube, k, frames, T,
                      extract_model=True, use_ind=True):
        vd, vdp = self._bind()
        self.solver.push()
        self.solver.add(frames.get_R(k - 1, vd))
        if use_ind:
            self.solver.add(Not(cube_to_expr(cube, vd)))
        self.solver.add(T(vd, vdp))
        self.solver.add(cube_to_expr(cube, vdp))

        if self.solver.check() == sat:
            if extract_model:
                m = self.solver.model()
                pred = extract_cube(m, vd, self.variables)
                iv = self.ckt.input_vars()
                ival = {n: (1 if is_true(m.eval(iv[n], model_completion=True)) else 0)
                        for n in self.ckt.inputs}
                self.solver.pop()
                if self.use_ternary:
                    pred01 = {v: (1 if pred[v] else 0) for v in self.variables}
                    self.stats['minterms'] += 1
                    self.stats['lits_in'] += len(pred)
                    pred = self._ternary_predecessor(pred01, ival, cube)
                    self.stats['lits_out'] += len(pred)
                return ('pred', pred)
            self.solver.pop()
            return ('pred', None)
        else:
            self.solver.pop()
            return ('blocked', None)

    def generalize(self, cube, k, frames, T, init_expr):
        cube = dict(cube)
        for v in list(cube.keys()):
            smaller = {k2: v2 for k2, v2 in cube.items() if k2 != v}
            if not smaller:
                continue
            if self.isInitial(smaller, init_expr):
                continue
            status, _ = self.solveRelative(
                smaller, k, frames, T,
                extract_model=False, use_ind=True
            )
            if status == 'blocked':
                del cube[v]
        return cube


    def _report_ternary(self):
        s = self.stats
        if self.use_ternary and s['minterms'] > 0:
            print(f'[ternary simulation] {s["minterms"]} minterms shrunk: '
                f'{s["lits_in"]} -> {s["lits_out"]} literals via '
                f'{s["probes"]} three-valued probes (no SAT calls).')

