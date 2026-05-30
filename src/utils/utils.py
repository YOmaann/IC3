from z3 import *


def bind(variables):
    v = {x: Bool(x) for x in variables}
    vp = {x: Bool(f'{x}_next') for x in variables}
    return v, vp


def extract_cube(model, vd, variables):
    cube = {}
    for v in variables:
        val = model.eval(vd[v], model_completion=True)
        cube[v] = is_true(val)
    return cube


def cube_to_expr(cube, vd):
    lits = []
    for v, val in cube.items():
        lits.append(vd[v] if val else Not(vd[v]))
    if not lits:
        return BoolVal(True)
    return And(*lits)


def negate_cube(cube, vd):
    lits = []
    for v, val in cube.items():
        lits.append(Not(vd[v]) if val else vd[v])
    if not lits:
        return BoolVal(False)
    return Or(*lits)


def subsumes(a, b):
    return a.items() <= b.items()


def fmt_cube(cube):
    if not cube:
        return "true"
    return " & ".join(n if v else "~" + n for n, v in cube.items())