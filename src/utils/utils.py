from z3 import *
import time
from rich.table import Table
from rich import box


def invariant_size(inv):
    clauses = inv.children() if is_and(inv) else [inv]
    literals = sum(len(c.children()) if is_or(c) else 1 for c in clauses)
    return len(clauses), literals


def build_stats(verdict, frames, Z, t0, fixpoint=None, inv=None):
    stats = {
        'verdict': verdict,
        'frames': frames.depth(),
        'fixpoint_frame': fixpoint,
        'cubes_learned': frames.learned,
        'clauses_live': frames.total_clauses(),
        'sat_calls': Z.stats['sat_calls'],
        'ternary_minterms': Z.stats['minterms'],
        'ternary_probes': Z.stats['probes'],
        'inv_clauses': 0,
        'inv_literals': 0,
        'time_s': time.perf_counter() - t0,
    }
    if inv is not None:
        stats['inv_clauses'], stats['inv_literals'] = invariant_size(inv)
    return stats


def make_finish(frames, Z, t0):
    def finish(verdict, result, fixpoint=None, inv=None):
        return result, build_stats(verdict, frames, Z, t0, fixpoint=fixpoint, inv=inv)
    return finish


def make_report(on_update, frames, Z, t0):
    def report():
        if on_update:
            on_update(build_stats('running', frames, Z, t0))
    return report


def make_on_update(progress, task, name):
    def on_update(s):
        progress.update(task, description=(
            f"[i]{name}[/i] — frame [b]{s['frames']}[/b] | "
            f"clauses learned [b]{s['cubes_learned']}[/b] | "
            f"SAT [b]{s['sat_calls']}[/b]"))
    return on_update


def _onoff(enabled):
    return "[green]on[/green]" if enabled else "[red]off[/red]"


def print_parameters(console, args):
    table = Table(title="Run configuration", box=box.ROUNDED,
                  title_style="bold magenta", show_header=True,
                  header_style="bold cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value")
    table.add_row("Target", str(args.file))
    table.add_row("Max frames", str(args.max_frames))
    table.add_row("Timeout", f"{args.timeout}s" if args.timeout > 0 else "none")
    table.add_row("Frame propagation", _onoff(not args.no_propagate))
    table.add_row("Ternary generalization", _onoff(not args.no_ternary))
    table.add_row("Unsat-core generalization", _onoff(args.use_unsatcore))
    table.add_row("Max latches", str(args.max_latches))
    console.print(table)


def print_runtime_stats(console, path, parsed, stats):
    table = Table(title=f"Runtime statistics — {path.name}", box=box.ROUNDED,
                  title_style="bold magenta", show_header=True,
                  header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Verdict", str(stats['verdict']))
    table.add_section()
    table.add_row("Latches", str(parsed['L']))
    table.add_row("Inputs", str(parsed['I']))
    table.add_row("And gates", str(parsed['A']))
    table.add_row("Constraints", str(parsed['C']))
    table.add_section()
    table.add_row("Frames built", str(stats['frames']))
    table.add_row("Fixpoint frame", str(stats['fixpoint_frame']))
    table.add_row("Clauses learned", str(stats['cubes_learned']))
    table.add_row("Live clauses", str(stats['clauses_live']))
    table.add_row("SAT calls", str(stats['sat_calls']))
    table.add_row("Ternary minterms", str(stats['ternary_minterms']))
    table.add_row("Ternary probes", str(stats['ternary_probes']))
    table.add_row("Invariant clauses", str(stats['inv_clauses']))
    table.add_row("Invariant literals", str(stats['inv_literals']))
    table.add_row("Runtime", f"{stats['time_s']:.3f}s")
    console.print(table)


def print_suite_summary(console, results):
    table = Table(title="Suite results", box=box.ROUNDED,
                  title_style="bold magenta", show_header=True,
                  header_style="bold cyan")
    table.add_column("File", style="bold")
    table.add_column("Verdict")
    table.add_column("Frames", justify="right")
    table.add_column("Clauses", justify="right")
    table.add_column("SAT", justify="right")
    table.add_column("Time", justify="right")
    for name, verdict, stats in results:
        if stats is None:
            table.add_row(name, verdict, "-", "-", "-", "-")
        else:
            table.add_row(name, stats['verdict'], str(stats['frames']),
                          str(stats['cubes_learned']), str(stats['sat_calls']),
                          f"{stats['time_s']:.2f}s")
    console.print(table)


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