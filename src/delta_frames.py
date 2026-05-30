from z3 import *
import heapq
from utils.utils import *

class DeltaFrames:
    def __init__(self, init_expr, variables):
        self.init_expr = init_expr
        self.variables = variables
        self.F = [[]]

    def depth(self):
        return len(self.F) - 1

    def new_frame(self):
        self.F.append([])

    def get_R(self, k, vd):
        if k == 0:
            return self.init_expr
        clauses = []
        for i in range(k, len(self.F)):
            for cube in self.F[i]:
                clauses.append(negate_cube(cube, vd))
        if not clauses:
            return BoolVal(True)
        return And(*clauses)

    def add_blocked_cube(self, k, cube):
        k = min(k, self.depth())
        if k < 1:
            return False
        for existing in self.F[k]:
            if subsumes(existing, cube):
                return False
        self.F[k] = [c for c in self.F[k] if not subsumes(cube, c)]
        self.F[k].append(cube)
        return True

    def is_cube_blocked(self, k, cube):
        for i in range(k, len(self.F)):
            for existing in self.F[i]:
                if subsumes(existing, cube):
                    return True
        return False

    def print_frames(self):
        for i in range(1, len(self.F)):
            if self.F[i]:
                cubes = ', '.join(f'({fmt_cube(c)})' for c in self.F[i])
                print(f'    F[{i}]  ({len(self.F[i])} blocked): {cubes}')