import time
from z3 import *
from utils.utils import *
from circuit import *

class IncrementalSolver:
    def __init__(self, variables, ckt, use_ternary=True, timeout_s=0):
        self.solver = Solver()
        self.variables = variables
        self.ckt = ckt                       # the circuit, for ternary simulation
        self.use_ternary = use_ternary
        self.deadline = (time.monotonic() + timeout_s) if timeout_s and timeout_s > 0 else None
        self.stats = {'minterms': 0, 'lits_in': 0, 'lits_out': 0, 'probes': 0,
                      'sat_calls': 0}
        self.vd, self.vdp = bind(variables)
        self.act_T = Bool('__trans_act')
        self.solver.add(Implies(self.act_T, ckt.T()(self.vd, self.vdp)))
        self.acts = {}

    def _check(self, *assumptions):
        self.stats['sat_calls'] += 1
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('timeout')
            self.solver.set('timeout', max(1, int(remaining * 1000)))
        result = self.solver.check(*assumptions)
        if result == unknown:
            raise TimeoutError('timeout')
        return result

    def _bind(self):
        return self.vd, self.vdp

    def _act(self, k):
        if k not in self.acts:
            self.acts[k] = Bool(f'__frame_act_{k}')
        return self.acts[k]

    def add_frame_clause(self, k, cube):
        self.solver.add(Or(Not(self._act(k)), negate_cube(cube, self.vd)))

    def _assume_R(self, k):
        return [act for i, act in self.acts.items() if i >= k]

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

    def _ternary_bad(self, bad01, ival):
        a = dict(bad01)
        a.update(ival or {})
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
        self.solver.add(Not(P_expr))
        result = None
        ival = None
        if self._check(self._assume_R(N)) == sat:
            m = self.solver.model()
            result = extract_cube(m, vd, self.variables)
            iv = self.ckt.input_vars()
            ival = {n: (1 if is_true(m.eval(iv[n], model_completion=True)) else 0)
                    for n in self.ckt.inputs}
        self.solver.pop()
        if result is not None and self.use_ternary:
            bad01 = {v: (1 if result[v] else 0) for v in self.variables}
            self.stats['minterms'] += 1
            self.stats['lits_in'] += len(result)
            result = self._ternary_bad(bad01, ival)
            self.stats['lits_out'] += len(result)
        return result

    def isInitial(self, cube, init_expr):
        vd, _ = self._bind()
        self.solver.push()
        self.solver.add(init_expr)
        self.solver.add(cube_to_expr(cube, vd))
        res = self._check() == sat
        self.solver.pop()
        return res

    def solveRelative(self, cube, k, frames, T,
                      extract_model=True, use_ind=True, core=False, init_expr=None):
        vd, vdp = self._bind()
        self.solver.push()
        if use_ind:
            self.solver.add(Not(cube_to_expr(cube, vd)))

        acts, cube_assumps = {}, []
        if core:
            for var, val in cube.items():
                act = Bool(f'__act_{var}')
                self.solver.add(Implies(act, vdp[var] if val else Not(vdp[var])))
                acts[act.decl().name()] = var
                cube_assumps.append(act)
        else:
            self.solver.add(cube_to_expr(cube, vdp))

        if k - 1 == 0:
            self.solver.add(frames.init_expr)
            base = [self.act_T]
        else:
            base = self._assume_R(k - 1) + [self.act_T]

        if self._check(base + cube_assumps) == sat:
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

        if not core:
            self.solver.pop()
            return ('blocked', None)

        unsat = self.solver.unsat_core()
        self.solver.pop()
        gen = {acts[c.decl().name()]: cube[acts[c.decl().name()]]
               for c in unsat if c.decl().name() in acts}
        for var, val in cube.items():
            if not self.isInitial(gen, init_expr):
                break
            gen[var] = val
        return ('blocked', gen)

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

