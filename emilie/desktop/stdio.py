"""Keep a process's stdin/stdout pipes for the protocol only.

On Windows a thread blocked reading an inherited pipe makes CreateProcess hang for every child that inherits it
(git, taskkill, ffmpeg ... would freeze), and a child that inherits stdout could print into the protocol. So the
pipes are moved to private, non-inheritable copies and fds 0/1 are pointed at NUL / stderr for everything else.
"""
from __future__ import annotations

import os
import sys


def private_stdio(take_stdin: bool = True):
    """-> (protocol input or None, protocol output). After this, print() and child processes use stderr."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", errors="replace", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    inp = None
    if take_stdin:
        inp = os.fdopen(os.dup(0), "r", encoding="utf-8", errors="replace")
        nul = os.open(os.devnull, os.O_RDONLY)
        os.dup2(nul, 0)
        os.close(nul)
        sys.stdin = open(os.devnull, "r")
    return inp, out
