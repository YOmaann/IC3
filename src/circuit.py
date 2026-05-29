from z3 import *

X = 'X'   

def t_not(a):       
  return X if a is X else 1 - a
def t_and(vals):
    if any(v == 0 for v in vals): return 0
    if any(v is X for v in vals): return X
    return 1
def t_or(vals):
    if any(v == 1 for v in vals): return 1
    if any(v is X for v in vals): return X
    return 0
def t_xor(a, b):    return X if (a is X or b is X) else a ^ b
def t_xnor(a, b):   return X if (a is X or b is X) else int(a == b)
def t_ite(c, a, b):
    if c == 1: return a
    if c == 0: return b
    return a if (a is not X and a == b) else X      # c is X


def ternary_eval(e, assign, memo):
    """Three-valued value (0/1/X) of the boolean Z3 expression `e` under
    `assign` ({leaf-name -> 0/1/X})."""
    eid = e.get_id()
    if eid in memo:
        return memo[eid]
    k = e.decl().kind()
    if k == Z3_OP_TRUE:
        v = 1
    elif k == Z3_OP_FALSE:
        v = 0
    elif k == Z3_OP_UNINTERPRETED:    # leaf: a Bool variable
        if e.num_args() != 0:
            raise ValueError(f'unsupported non-constant application: {e}')
        name = e.decl().name()
        if name not in assign:
            raise ValueError(f'no value assigned to leaf {name!r}')
        v = assign[name]
    elif k == Z3_OP_NOT:
        v = t_not(ternary_eval(e.arg(0), assign, memo))
    elif k == Z3_OP_AND:
        v = t_and([ternary_eval(e.arg(i), assign, memo) for i in range(e.num_args())])
    elif k == Z3_OP_OR:
        v = t_or([ternary_eval(e.arg(i), assign, memo) for i in range(e.num_args())])
    elif k == Z3_OP_XOR:
        v = t_xor(ternary_eval(e.arg(0), assign, memo),
                  ternary_eval(e.arg(1), assign, memo))
    elif k in (Z3_OP_EQ, Z3_OP_IFF):  # boolean equality == XNOR
        if e.num_args() != 2:
            raise ValueError(f'unsupported n-ary equality: {e}')
        v = t_xnor(ternary_eval(e.arg(0), assign, memo),
                   ternary_eval(e.arg(1), assign, memo))
    elif k == Z3_OP_DISTINCT and e.num_args() == 2:   # distinct(a,b) == XOR
        v = t_xor(ternary_eval(e.arg(0), assign, memo),
                  ternary_eval(e.arg(1), assign, memo))
    elif k == Z3_OP_ITE:
        v = t_ite(ternary_eval(e.arg(0), assign, memo),
                  ternary_eval(e.arg(1), assign, memo),
                  ternary_eval(e.arg(2), assign, memo))
    elif k == Z3_OP_IMPLIES:
        v = t_or([t_not(ternary_eval(e.arg(0), assign, memo)),
                  ternary_eval(e.arg(1), assign, memo)])
    else:
        raise ValueError(f'unsupported Z3 op (kind {k}) in circuit: {e}')
    memo[eid] = v
    return v


class Circuit:
    """An FSM whose logic is given as Z3 boolean expressions.

      state : list of state-flop names (Bool variable names)
      inputs: list of primary-input names (Bool variable names)
      next  : {flop_name: Z3 expr}  next-state function over current flops + inputs
      init  : Z3 expr   predicate describing the initial states
      prop  : Z3 expr   the property P (the design is "good" when P holds)

    Example:
        b0 = Bool('b0'); b1 = Bool('b1')
        ckt = Circuit(state=['b0','b1'], inputs=[],
                      next={'b0': Not(b0), 'b1': BoolVal(False)},
                      init=And(Not(b0), Not(b1)), prop=Not(b1))
"""
    def __init__(self, state, inputs, next, init, prop):
        self.state, self.inputs = list(state), list(inputs)
        self.next, self.init, self.prop = dict(next), init, prop

    def input_vars(self):
        return {n: Bool(n) for n in self.inputs}

    def T(self):
        def _T(vd, vdp):
            return And(*[vdp[v] == self.next[v] for v in self.state])
        return _T

    def init_z3(self, vd): return self.init
    def prop_z3(self, vd): return self.prop

    def ternary_step(self, sval, ival):
        assign = dict(sval)
        assign.update(ival)
        memo = {}
        return {v: ternary_eval(self.next[v], assign, memo) for v in self.state}

    def ternary_prop(self, sval):
        return ternary_eval(self.prop, dict(sval), {})
