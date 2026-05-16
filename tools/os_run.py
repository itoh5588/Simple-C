"""Smoke runner for the hybrid OS via pty.

emu.py uses termios and runs interactively. To exercise OS commands
without a human, spawn it inside a pty, send keystrokes, and verify
the expected substring appears in the captured output within a
per-step timeout.

Covers VC0 (cmdloop): welcome, ls, date, exec hello, exit.
Covers VC1 (taskexec sleep.bin) and VC2 (taskexec pagefault.bin)
via Ctrl+] switching.
"""
import os
import pty
import select
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 5.0
ENTER = "\r"
CTRL_RBRACKET = "\x1d"  # Ctrl+] — VC switch prefix in emu.py

STEPS = [
    ("welcome",         None,                              "Welcome to Simple OS"),
    ("ls",              "ls" + ENTER,                      "hello.bin"),
    ("date",            "date" + ENTER,                    ":"),
    ("exec hello",      "exec hello.bin" + ENTER,          "Hello, World!"),
    ("taskexec sleep",  "taskexec sleep.bin" + ENTER,      "taskexec sleep.bin"),
    ("vc1 waiting",     CTRL_RBRACKET + "1",               "WAITING 1s"),
    ("vc0 after vc1",   CTRL_RBRACKET + "0",               "[VC 0"),
    ("taskexec pf",     "taskexec pagefault.bin" + ENTER,  "taskexec pagefault.bin"),
    ("vc2 pagefault",   CTRL_RBRACKET + "2",               "12345"),
    ("vc0 after vc2",   CTRL_RBRACKET + "0",               "[VC 0"),
    ("exit",            "exit" + ENTER,                    "CPU halted"),
]


def _read_until(fd, expect, buf):
    deadline = time.time() + TIMEOUT
    while expect not in buf:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError(
                f"timed out waiting for {expect!r}; tail={buf[-200:]!r}"
            )
        r, _, _ = select.select([fd], [], [], remaining)
        if not r:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError as e:
            raise TimeoutError(f"read failed before {expect!r}: {e}")
        if not chunk:
            raise TimeoutError(f"EOF before {expect!r}; tail={buf[-200:]!r}")
        buf += chunk.decode("utf-8", errors="replace")
    return buf


def main():
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.execvp(sys.executable, [sys.executable, "emu.py"])

    buf = ""
    failed = False
    try:
        for name, send, expect in STEPS:
            if send is not None:
                os.write(fd, send.encode("utf-8"))
            buf = _read_until(fd, expect, buf)
            print(f"OK   {name}: saw {expect!r}")
    except TimeoutError as e:
        print(f"FAIL {e}")
        failed = True
    finally:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
