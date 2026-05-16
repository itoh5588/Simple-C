"""Check Simple OS hybrid labels that must stay ABI-compatible."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


EXPECTED = {
    "cmp_str": 0xB0000,
    "get_nth_token": 0xB1000,
    "sleep": 0xB2000,
    "key_input": 0xB3000,
    "task_exit": 0xB4000,
    "keybuffer": 0xC0000,
    "tokenbuffer": 0xC1000,
    "vector_table": 0xFF800,
}

RANGED = {
    "os_cmdloop_c": (0xB0000, 0xB2000),
    "task_update_sleepers_c": (0xB5000, 0xC0000),
    "scheduler_select_next_task_c": (0xB5000, 0xC0000),
    "syscall_sleep_prepare_c": (0xB5000, 0xC0000),
    "syscall_task_exit_prepare_c": (0xB5000, 0xC0000),
    "vm_alloc_page_for_fault_c": (0xB5000, 0xC0000),
}


def load_asm_module():
    spec = importlib.util.spec_from_file_location("asm", ROOT / "asm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    asm = load_asm_module()
    source = (ROOT / "examples" / "os" / "simple_os_hybrid.asm").read_text(encoding="utf-8")
    asm._deferred_defs = []
    asm.first_pass(source)

    failed = False
    for name, expected in EXPECTED.items():
        actual = asm.symbol_table.get(name)
        if actual != expected:
            print(f"FAIL {name}: expected 0x{expected:05X}, got {actual!r}")
            failed = True
        else:
            print(f"OK   {name}=0x{actual:05X}")

    for name, (start, end) in RANGED.items():
        actual = asm.symbol_table.get(name)
        if actual is None:
            print(f"FAIL {name}: missing")
            failed = True
        elif not (start <= actual < end):
            print(
                f"FAIL {name}: expected 0x{start:05X} <= addr < 0x{end:05X}, "
                f"got 0x{actual:05X}"
            )
            failed = True
        else:
            print(f"OK   {name}=0x{actual:05X} in [0x{start:05X}, 0x{end:05X})")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
