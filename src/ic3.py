import heapq
from z3 import *
from utils.utils import *
from delta_frames import DeltaFrames
from incremental_solver import IncrementalSolver

def recBlockCube(Z, frames, T, P_expr, init_expr, bad_cube, start_frame):
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
            gen_cube = Z.generalize(cube, frame, frames, T, init_expr)
            frames.add_blocked_cube(frame, gen_cube)
            print(f'    Blocked at F[{frame}]: {gen_cube}')
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
            print(f'  Fixpoint: F[{k}] empty')
            return k

    return False  

# drop a variable from the formula
def drop_var(phi, v):
    # g = Goal()
    # t = Tactic('qe')
    # g.add(Exists(v, phi))
    return simplify(substitute(phi, (v, BoolVal(False))))


def PDR(ckt, do_propagate=True, max_frames=200, use_ternary=True):
    # if use_ternary = False then use unsat core
    variables = ckt.state
    vd, _ = bind(variables)
    T = ckt.T()                 
    init_expr = ckt.init_z3(vd)
    P_expr = ckt.prop_z3(vd)

    frames = DeltaFrames(init_expr, variables)
    Z = IncrementalSolver(variables, ckt, use_ternary=use_ternary)

    # Check Init => P
    Z.solver.push()
    Z.solver.add(init_expr)
    Z.solver.add(Not(P_expr))
    if Z.solver.check() == sat:
        Z.solver.pop()
        print('Init violates P.')
        return False
    Z.solver.pop()

    for _ in range(max_frames):
        frames.new_frame()
        N = frames.depth()
        print(f'\n=== Frame {N} >>>')

        while True:
            bad = Z.getBadCube(frames, P_expr)
            if bad is None:
                break
            print(f'  Bad: {bad}')
            if not recBlockCube(Z, frames, T, P_expr, init_expr, bad, N):
                print('\n** PROPERTY FAILS **')
                Z._report_ternary()
                return False

        print(f'  Frame {N} clean.')
        frames.print_frames()

        if do_propagate and N >= 2:
            k = propagate(Z, frames, T)
            if k:
                inv = simplify(frames.get_R(k, vd))
                if '__viol__' in vd:
                    inv = drop_var(inv, vd['__viol__'])
                print(f'\n* Property HOLDS *')
                print(f'Invariant: {inv}')
                Z._report_ternary()
                return inv

    print(f'Reached max_frames.')
    if use_ternary:
        Z._report_ternary()
    return None