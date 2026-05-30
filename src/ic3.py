import heapq
import time
from z3 import *
from utils.utils import *
from delta_frames import DeltaFrames
from incremental_solver import IncrementalSolver

set_option(max_args=10000000, max_lines=10000000,
           max_depth=10000000, max_visited=10000000)


def recBlockCube(Z, frames, T, P_expr, init_expr, bad_cube, start_frame,
                 use_ternary=True, use_unsatcore=False, report=None):
    counter = [0]
    Q = []

    def push(frame, cube):
        heapq.heappush(Q, (frame, counter[0], cube))
        counter[0] += 1

    push(start_frame, bad_cube)

    while Q:
        frame, _, cube = heapq.heappop(Q)

        if frame == 0:
            return False

        if frames.is_cube_blocked(frame, cube):
            continue

        status, pred = Z.solveRelative(
            cube, frame, frames, T, extract_model=True, use_ind=True
        )

        if status == 'blocked':
            # if use_ternary:
            #     gen_cube = Z.generalize(cube, frame, frames, T, init_expr)
            # else:
            #     gen_cube = Z.generalize_unsat(cube, frame, frames, T, init_expr)
            gen_cube = cube
            if use_ternary:
                gen_cube = Z.generalize(gen_cube, frame, frames, T, init_expr)
            if use_unsatcore:
                gen_cube = Z.generalize_unsat(gen_cube, frame, frames, T, init_expr)
            if frames.add_blocked_cube(frame, gen_cube):
                frames.learned += 1
            if report:
                report()
            print(f'      learned: frame {frame} can never reach  {fmt_cube(gen_cube)}')
            if frame < frames.depth():
                push(frame + 1, cube)
        else:
            assert pred is not None
            push(frame - 1, pred)
            push(frame, cube)

    return True


def propagate(Z, frames, T):
    N = frames.depth()
    for k in range(1, N):
        moved = []
        kept = []
        for cube in frames.F[k]:
            status, _ = Z.solveRelative(
                cube, k + 1, frames, T,
                extract_model=False, use_ind=False
            )
            if status == 'blocked':
                moved.append(cube)
            else:
                kept.append(cube)

        frames.F[k] = kept
        for cube in moved:
            frames.add_blocked_cube(min(k + 1, N), cube)

        if len(frames.F[k]) == 0:
            print(f'  fixpoint reached: frame {k} is empty, so R[{k}] = R[{k + 1}] is an inductive invariant.')
            return k

    return False  

# drop a variable from the formula
def drop_var(phi, v):
    # g = Goal()
    # t = Tactic('qe')
    # g.add(Exists(v, phi))
    return simplify(substitute(phi, (v, BoolVal(False))))


def PDR(ckt, do_propagate=True, max_frames=200, use_ternary=True, use_unsatcore=False,
        on_update=None):
    variables = ckt.state
    vd, _ = bind(variables)
    T = ckt.T()                 
    init_expr = ckt.init_z3(vd)
    P_expr = ckt.prop_z3(vd)

    frames = DeltaFrames(init_expr, variables)
    Z = IncrementalSolver(variables, ckt, use_ternary=use_ternary)
    t0 = time.perf_counter()
    finish = make_finish(frames, Z, t0)
    report = make_report(on_update, frames, Z, t0)

    # Check Init => P
    Z.solver.push()
    Z.solver.add(init_expr)
    Z.solver.add(Not(P_expr))
    if Z._check() == sat:
        Z.solver.pop()
        print('  the initial state already violates the property')
        return finish('UNSAFE', False)
    Z.solver.pop()

    for _ in range(max_frames):
        frames.new_frame()
        N = frames.depth()
        print(f'\nFrame {N}: extending the trace >>>')

        while True:
            bad = Z.getBadCube(frames, P_expr)
            if bad is None:
                break
            print(f'  found a state that leads to a violation. trying to block it: {fmt_cube(bad)}')
            if not recBlockCube(Z, frames, T, P_expr, init_expr, bad, N,
                                 use_ternary=use_ternary, use_unsatcore=use_unsatcore,
                                 report=report):
                print('\n* PROPERTY FAILS: a bad state is reachable from the initial states. *')
                Z._report_ternary()
                return finish('UNSAFE', False)

        print(f'  frame {N} is clean: no property violation is reachable within {N} steps.')
        frames.print_frames()
        report()

        if do_propagate and N >= 2:
            k = propagate(Z, frames, T)
            if k:
                inv = simplify(frames.get_R(k, vd))
                if '__viol__' in vd:
                    inv = drop_var(inv, vd['__viol__'])
                print('\n*PROPERTY HOLDS: found an inductive invariant.*')
                print(f'  invariant (frame {k}): {inv}')
                Z._report_ternary()
                return finish('SAFE', inv, fixpoint=k, inv=inv)

    print(f'  reached the {max_frames}-frame limit without deciding.')
    if use_ternary:
        Z._report_ternary()
    return finish('UNKNOWN', None)