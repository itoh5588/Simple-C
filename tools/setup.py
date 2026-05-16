"""Fetch the book's CPU emulator and OS source into vendor/book/.

Simple-C and Simple OS in C are derivative works built on top of the
custom 32-bit CPU, assembler, and OS from the book 『いちばんやさしい！
OS自作超入門』(末安 泰三 著、日経BP). This repository contains only
our own work; the book's reference implementation is fetched from
its upstream GitHub repository at setup time.

Steps performed:
  1. Clone the upstream repository into vendor/book/ at a pinned
     commit. If the upstream URL fails, fall back to a personal mirror.
  2. Apply our local patch to emu.py (small \\r-handling fix; reported
     upstream as a GitHub Issue).
  3. Symlink the book files we use (asm.py, emu.py, os.asm, sleep.asm,
     pagefault.asm) into the repo root so build scripts can run with
     simple relative paths.

Re-running is safe; the script is idempotent.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "book"
PATCH_DIR = ROOT / "tools" / "patches"

# Upstream sources, tried in order. The pinned commit is the one we
# tested Simple-C against. Bumping it means re-running the full test
# suite.
BOOK_COMMIT = "5542998"
BOOK_SOURCES = [
    "https://github.com/sueyasu/os_book_code",         # 本家 (upstream)
    "https://github.com/itoh5588/os_book_code",        # 保険 (personal mirror)
]

# Book files we symlink into the repo root.
LINKED_FILES = [
    "asm.py",
    "emu.py",
    "os.asm",
    "sleep.asm",
    "pagefault.asm",
]

PATCHES = [
    PATCH_DIR / "emu_cr_fix.patch",
]


def run(cmd, cwd=None, check=True):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=cwd, check=check)


def clone_upstream():
    """Try each BOOK_SOURCES URL in turn until one clones successfully."""
    if VENDOR.exists() and (VENDOR / ".git").exists():
        print(f"vendor/book already cloned, skipping clone")
        return
    VENDOR.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for url in BOOK_SOURCES:
        try:
            run(["git", "clone", url, str(VENDOR)])
            return
        except subprocess.CalledProcessError as err:
            last_err = err
            print(f"clone from {url} failed, trying next source")
            if VENDOR.exists():
                shutil.rmtree(VENDOR)
    raise RuntimeError("All upstream sources failed") from last_err


def checkout_pinned():
    run(["git", "fetch", "--all"], cwd=VENDOR)
    run(["git", "checkout", BOOK_COMMIT], cwd=VENDOR)


def apply_patches():
    for patch in PATCHES:
        if not patch.exists():
            print(f"patch {patch.name} not found, skipping")
            continue
        # `git apply --check` to detect already-applied patches
        result = subprocess.run(
            ["git", "apply", "--check", "-R", str(patch)],
            cwd=VENDOR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            print(f"patch {patch.name} already applied")
            continue
        run(["git", "apply", str(patch)], cwd=VENDOR)


def make_symlinks():
    for name in LINKED_FILES:
        src = VENDOR / name
        if not src.exists():
            raise RuntimeError(f"expected {src} in upstream but it's missing")
        dst = ROOT / name
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        # Use relative symlink so the project is portable.
        rel_src = os.path.relpath(src, ROOT)
        dst.symlink_to(rel_src)
        print(f"linked {name} -> {rel_src}")


def main():
    clone_upstream()
    checkout_pinned()
    apply_patches()
    make_symlinks()
    print()
    print("Setup complete. Next: python tools/build_simple_os.py")


if __name__ == "__main__":
    main()
