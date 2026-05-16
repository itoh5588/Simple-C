"""Build a Simple OS hybrid asm without editing tracked os.asm.

The script reads:
  - os.asm: original OS source
  - simple_os.asm: generated C/asm replacement for selected system functions

and writes:
  - simple_os_hybrid.asm: original OS with the 0xB0000-0xB1FFF system
    function region replaced by the generated Simple OS version.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "os.asm"
GENERATED = ROOT / "examples" / "os" / "simple_os.asm"
OUTPUT = ROOT / "examples" / "os" / "simple_os_hybrid.asm"


def find_line(lines, predicate, start=0):
    for i in range(start, len(lines)):
        if predicate(lines[i]):
            return i
    raise RuntimeError("required marker not found")


def is_addr(line, addr):
    parts = line.strip().split()
    return len(parts) >= 2 and parts[0].upper() == ".ADDR" and parts[1].lower() == addr


def main():
    original = ORIGINAL.read_text(encoding="utf-8").splitlines()
    generated = GENERATED.read_text(encoding="utf-8").splitlines()

    orig_start = find_line(original, lambda line: is_addr(line, "0xb0000"))
    orig_end = find_line(original, lambda line: is_addr(line, "0xc0000"), orig_start + 1)

    gen_start = find_line(generated, lambda line: is_addr(line, "0xb0000"))
    gen_end = len(generated)

    generated_region = generated[gen_start:gen_end]

    cmd_start = find_line(original, lambda line: line.strip() == "cmdloop:")
    cmd_end = find_line(original, lambda line: line.strip() == "; Handler", cmd_start + 1)
    cmd_replacement = [
        "cmdloop:",
        "        CALLI   os_cmdloop_c",
        "        HALT",
        "",
    ]

    merged = (
        original[:cmd_start]
        + cmd_replacement
        + original[cmd_end:orig_start]
        + generated_region
        + [""]
        + original[orig_end:]
    )

    sleep_start = find_line(merged, lambda line: line.strip() == "_sleep_proc:")
    sleep_end = find_line(merged, lambda line: line.strip() == "_timeslice_proc:", sleep_start + 1)
    sleep_replacement = [
        "_sleep_proc:",
        "        PUSH    R0",
        "        PUSH    R1",
        "        PUSH    R2",
        "        PUSH    R3",
        "        CALLI   task_update_sleepers_c",
        "        POP     R3",
        "        POP     R2",
        "        POP     R1",
        "        POP     R0",
        "",
    ]
    merged = merged[:sleep_start] + sleep_replacement + merged[sleep_end:]

    save_sp = find_line(merged, lambda line: line.strip() == "_save_sp:")
    find_start = find_line(merged, lambda line: line.strip() == "MOVI    R2, 0", save_sp + 1)
    find_end = find_line(merged, lambda line: line.strip() == "_select_next:", find_start + 1)
    select_replacement = [
        "        CALLI   scheduler_select_next_task_c",
    ]
    merged = merged[:find_start] + select_replacement + merged[find_end:]

    pf_start = find_line(merged, lambda line: line.strip() == "DIVI    R8, 0x10000")
    pf_end = find_line(merged, lambda line: line.strip() == "POP     R8", pf_start + 1)
    pf_replacement = [
        "        DIVI    R8, 0x10000",
        "        PUSH    R8",
        "        CALLI   vm_alloc_page_for_fault_c",
        "        ADDI    SP, 4",
        "",
    ]
    merged = merged[:pf_start] + pf_replacement + merged[pf_end:]

    OUTPUT.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
