; ── C ランタイムライブラリ ────────────────────────
; cc.py が生成する asm の末尾に取り込まれる。
; 呼出規約: 引数はスタック、戻り値は R0、callee-saved R4〜R7。

; putchar(c) — 1文字出力
putchar:
        PUSH    R7
        MOV     R7, SP
        MOV     R8, R7
        ADDI    R8, 8
        LDD     R8, [R8]
        SYSCALL 0
        MOV     SP, R7
        POP     R7
        RET

; puts(s) — NUL 終端文字列を出力（改行は付けない）
puts:
        PUSH    R7
        MOV     R7, SP
        MOV     R8, R7
        ADDI    R8, 8
        LDD     R8, [R8]
        SYSCALL 1
        MOV     SP, R7
        POP     R7
        RET

; getchar() — 1文字入力（ブロッキング）
; SYSCALL 3 が 0 を返すと再試行
getchar:
        SYSCALL 3
        SBTI    R8, 0
        JPZI    getchar
        MOV     R0, R8
        RET

; printd(n) — n を 10進で出力（符号無し）
printd:
        PUSH    R7
        MOV     R7, SP
        MOV     R8, R7
        ADDI    R8, 8
        LDD     R8, [R8]
        MOVI    R9, _printd_fmt
        SYSCALL 2
        MOV     SP, R7
        POP     R7
        RET
_printd_fmt:
        .BYTE   0

; printx(n) — n を 16進で出力（先頭 0x 付き）
printx:
        PUSH    R7
        MOV     R7, SP
        MOV     R8, R7
        ADDI    R8, 8
        LDD     R8, [R8]
        MOVI    R9, _printx_fmt
        SYSCALL 2
        MOV     SP, R7
        POP     R7
        RET
_printx_fmt:
        .BYTE   35      ; '#'
        .BYTE   120     ; 'x'
        .BYTE   0

; exit() — 終了。HALT で停止する
exit:
        HALT
