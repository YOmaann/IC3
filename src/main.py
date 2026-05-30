from rich import print as r_print
from rich.progress import Progress, SpinnerColumn, TextColumn, TaskProgressColumn, BarColumn, TimeElapsedColumn
from rich.console import Console, Group
from rich.live import Live
from rich.layout import Layout
import argparse
from utils.print import print
from utils.timeout import handler
from utils.utils import (make_on_update, 
                            print_suite_summary,
                            print_parameters, 
                            print_runtime_stats)
from aiger import sanitize_aiger_file, load_aiger_file, aiger_to_circuit
from pathlib import Path
import signal, contextlib, io, os, sys
from ic3 import PDR

# Rich configurations
console = Console(file=sys.stdout)
progress = Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    TimeElapsedColumn(),
    console=console,
)
overall = Progress(
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    console=console,
)
group_progress = Group(
    overall, progress
)

verify_task_progress = overall.add_task("Verifying suite", total=None)


def status_icon(verdict):
    if verdict.startswith("SAFE"):
        return "[green]SAFE:[/green]"
    if verdict.startswith("UNSAFE"):
        return "[red]UNSAFE:[/red]"
    return "[yellow]?[/yellow]"

layout = Layout(
    name="root",
    ratio=1,
)
layout.split(
    Layout(name="header", size=3),
    Layout(name="main", ratio=1)
)

# per file PDR
def verify_aiger_file(path, out_dir, task, max_frames, no_propagate, timeout_s, no_ternary, use_unsatcore):
    progress.update(task, description=f"Loading [i]{path.name}[/i]...")
    parsed, ckt = load_aiger_file(path)
    if not parsed:
        console.print(f'[red]Failed to load "{path.name}".[/red]')
        return 'ERROR', None, None

    progress.update(task, description=f"Verifying [i]{path.name}[/i]...")
    on_update = make_on_update(progress, task, path.name)

    stats = None
    try:
        log_path = out_dir / f'{path.stem}.log'
        with open(log_path, 'w') as logf, contextlib.redirect_stdout(logf):
            inv, stats = PDR(ckt, do_propagate=not no_propagate,
                             max_frames=max_frames, use_ternary=not no_ternary,
                             use_unsatcore=use_unsatcore, on_update=on_update,
                             timeout_s=timeout_s)
        verdict = ('UNSAFE' if inv is False
                   else 'SAFE : property holds' if inv is not None
                   else 'UNKNOWN (frame bound reached)')
    except TimeoutError:
        verdict = f'TIMEOUT after {timeout_s}s'

    return verdict, stats, parsed

parser = argparse.ArgumentParser()
parser.add_argument('file', nargs='?', default=None,
                    help="AIGER file to verify.")
parser.add_argument('--max-frames', type=int, default=100,
                    help="Maximum number of frames to explore.")
parser.add_argument('--no-propagate', action='store_true',
                    help="Disable frame propagation.")
parser.add_argument('--timeout', type=int, default=0,
                    help="Timeout in seconds for the verification process.")
parser.add_argument('--no-ternary', action='store_true',
                    help="Disable ternary simulation.")
parser.add_argument('--use-unsatcore', action='store_true',
                    help="Enable unsat-core generalization of blocked cubes.")
parser.add_argument('--max-latches', type=int, default=1000,
                    help="Maximum number of latches allowed in the input aiger file.")

args = parser.parse_args()

r_print('Welcome to [bold magenta]ICEpie[/bold magenta] :)\n')
if not args.file:
    r_print('[red]Oops :0 Please provide either a file or a benchmark to verify.[/red]')
    r_print('''This is an implementation of IC3 in python as part of my masters thesis. It is not optimized for performance.
It is meant for me to understand and implement the algorithm and to experiment with optimizations.
            \n [yellow]Press -h to view help.[/yellow]''')

    exit()

print_parameters(console, args)
console.print()
parameters = [args.max_frames, args.no_propagate, args.timeout, args.no_ternary, args.use_unsatcore]
if args.file:
    path = Path(args.file)
    if path.is_file():
        out_dir = path.parent / 'output'
        out_dir.mkdir(parents=True, exist_ok=True)
        with progress:
            task = progress.add_task("", total=None)
            verdict, stats, parsed = verify_aiger_file(path, out_dir, task, *parameters)
            progress.remove_task(task)
        if stats is not None:
            print_runtime_stats(console, path, parsed, stats)
        console.print(f"{status_icon(verdict)} {path.name} :: {verdict}")
    elif path.is_dir():
        aiger_files = sorted(f for f in path.rglob("*") if f.suffix in [".aag", ".aig"])
        if not aiger_files:
            r_print(f'[red]No .aag/.aig files found under "{path}".[/red]')
            exit()
        out_dir = path / 'output'
        out_dir.mkdir(parents=True, exist_ok=True)
        overall.update(verify_task_progress, total=len(aiger_files))
        results = []
        with Live(group_progress, console=console):
            for file in aiger_files:
                task = progress.add_task("", total=None)
                verdict, stats, parsed = verify_aiger_file(file, out_dir, task, *parameters)
                progress.remove_task(task)
                console.print(f"{status_icon(verdict)} {file.name} :: {verdict}")
                overall.advance(verify_task_progress)
                results.append((file.name, verdict, stats))
        print_suite_summary(console, results)
    else:
        r_print('[red bold]ERROR:[/red bold] folder or file does not exist.')
            