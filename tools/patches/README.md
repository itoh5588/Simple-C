# Patches applied to the upstream book toolchain

These patches are applied by `tools/setup.py` to the cloned upstream
`vendor/book/` working tree. They fix issues we encountered and reported
upstream as GitHub Issues. When upstream merges them, the corresponding
patch will be removed here and `BOOK_COMMIT` in `setup.py` will be
bumped past the merge.

## emu_cr_fix.patch

`emu.py` `vc_write()` and `_tty_show_vc()` were replacing bare `\r`
(carriage return) with `\n`, which broke the OS command loop's prompt
redraw sequence `\x1b[2K\r> ` — every keystroke scrolled the screen
down one line. The fix limits normalisation to `\r\n` only, leaving
bare `\r` intact for row-refresh use.

Reported as Issue #1 on <https://github.com/sueyasu/os_book_code>.
