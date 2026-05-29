# Timeout handler
import signal, contextlib, io
from utils.print import r_print

def handler(signum, frame):
    raise TimeoutError("Timeout!")