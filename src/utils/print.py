import builtins
from rich import print as r_print

def print(str, verbose=False):
    if verbose:
        builtins.print(str)

def r_print(str, verbose=False):
    if verbose:
        r_print(str)