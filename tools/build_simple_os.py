"""Build Simple OS in C artifacts on top of the book toolchain.

Run `python tools/setup.py` first to fetch the upstream book repository
into vendor/book/ and symlink asm.py / emu.py / os.asm into the repo
root. This script then runs the hybrid build pipeline:

  1. compile examples/os/simple_os.c -> examples/os/simple_os.asm
  2. merge with os.asm into examples/os/simple_os_hybrid.asm
  3. assemble simple_os_hybrid.asm -> simple_os_hybrid.bin
  4. prepare os.bin for emu.py, which reads that fixed filename
  5. prepare sample task binaries under dir/
"""
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    run(["python", "cc.py", "--no-runtime", "examples/os/simple_os.c"])
    run(["python", "tools/build_simple_os_hybrid.py"])
    run(["python", "asm.py", "examples/os/simple_os_hybrid.asm"])
    run(["python", "tools/check_simple_os_labels.py"])

    run(["python", "cc.py", "samples/hello.c"])
    run(["python", "asm.py", "samples/hello.asm"])
    run(["python", "asm.py", "sleep.asm"])
    run(["python", "asm.py", "pagefault.asm"])

    (ROOT / "dir").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "examples/os/simple_os_hybrid.bin", ROOT / "os.bin")
    shutil.copyfile(ROOT / "samples/hello.bin", ROOT / "dir/hello.bin")
    shutil.copyfile(ROOT / "sleep.bin", ROOT / "dir/sleep.bin")
    shutil.copyfile(ROOT / "pagefault.bin", ROOT / "dir/pagefault.bin")

    print("Prepared os.bin and dir/{hello,sleep,pagefault}.bin")


if __name__ == "__main__":
    main()
