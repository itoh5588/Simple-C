/* simple_os.c — Simple OS の C 本体（hybrid C + asm）
 *
 * 書籍付属の os.asm のロジック部を C で書き直したファイル。残りの asm 部
 * （タスクスイッチ・割込ハンドラなど）は os.asm にそのまま残し、
 * tools/build_simple_os_hybrid.py が両者を結合して simple_os_hybrid.asm を作る。
 *
 * 命名規約:
 *   末尾 _c       : asm 側から CALLI で呼ばれる C 本体
 *   os_label_*    : ラベルアドレスを R0 に置くだけのヘルパ
 *                   （ccgen.py が inline-asm builtin として展開、CALL/RET なし）
 *   os_* (他)     : 対応する SYSCALL を呼ぶ薄いラッパ
 *
 * 公開アドレス（os.asm からも参照される ABI）:
 *   0xB0000 cmp_str       / 0xB1000 get_nth_token / 0xB2000 sleep
 *   0xB3000 key_input     / 0xB4000 task_exit     / 0xB5000〜 C 関数群
 *
 * 主要メモリ領域:
 *   0xC0000 keybuffer (コマンド入力) / 0xC1000 tokenbuffer
 *   0xFFF00 ページテーブル基点（タスク tid のエントリは +tid*0x10）
 */

asm(".DEF key_input 0xB3000");

/* cmp_str (0xB0000) — caller-saved レジスタを退避して cmp_str_c を呼び、
 * 結果 (1=不一致 / 0=一致) を CR の Z フラグに反映させて返すラッパ。
 * 戻り値はゼロ判定用なので R0 は破棄して POP で復元する。 */
asm(".ADDR 0xB0000\ncmp_str:\n        PUSH    R0\n        PUSH    R1\n        PUSH    R2\n        PUSH    R3\n        PUSH    R9\n        PUSH    R8\n        CALLI   cmp_str_c\n        ADDI    SP, 8\n        SBTI    R0, 0\n        POP     R3\n        POP     R2\n        POP     R1\n        POP     R0\n        RET");

/* 2 つの NUL 終端文字列を 1 バイトずつ比較。
 * 戻り値: 0 = 等しい、 1 = どこかで不一致。長さも内容も同じなら 0。 */
int cmp_str_c(char *a, char *b) {
    while (*a == *b) {
        if (*a == 0) {
            return 0;
        }
        a++;
        b++;
    }
    return 1;
}

/* get_nth_token (0xB1000) — get_nth_token_c のラッパ。戻り値（tokenbuffer
 * アドレス）を R8 経由でも返す。 */
asm(".ADDR 0xB1000\nget_nth_token:\n        PUSH    R0\n        PUSH    R1\n        PUSH    R2\n        PUSH    R3\n        PUSH    R9\n        PUSH    R8\n        CALLI   get_nth_token_c\n        ADDI    SP, 8\n        MOV     R8, R0\n        POP     R3\n        POP     R2\n        POP     R1\n        POP     R0\n        RET");

/* input から n 番目（1 始まり）のホワイトスペース区切りトークンを取り出し、
 * tokenbuffer (0xC1000) に NUL 終端でコピーして返す。
 * 区切り文字は TAB (9) と SPACE (32)。
 * 引数: n        — 1 始まりのトークン番号
 *       input    — 入力文字列の先頭
 * 戻り値: 常に 0xC1000（コピー先固定）。トークンが存在しないときは
 *         tokenbuffer に空文字列を書いて 0xC1000 を返す。 */
int get_nth_token_c(int n, char *input) {
    char *p;
    char *start;
    char *out;
    int in_token;
    int c;

    p = input;
    start = 0;
    out = 0xC1000;
    in_token = 0;

    while (n > 0) {
        while (1) {
            c = *p;
            if (c == 0) {
                *out = 0;
                return 0xC1000;
            }
            if (c == 9 || c == 32) {
                if (in_token) {
                    in_token = 0;
                }
                p++;
                continue;
            }
            if (!in_token) {
                in_token = 1;
                start = p;
                break;
            }
            p++;
        }
        n--;
    }

    while (1) {
        c = *start;
        *out = c;
        if (c == 9 || c == 32 || c == 0) {
            *out = 0;
            return 0xC1000;
        }
        out++;
        start++;
    }
}

/* SYSCALL 0: c (R8) を現タスクの仮想コンソールに 1 文字出力。 */
int os_print_char(int c) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("SYSCALL 0");
    return 0;
}

/* SYSCALL 1: NUL 終端文字列 s (R8) を現タスクの VC に出力。 */
int os_print_string(char *s) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("SYSCALL 1");
    return 0;
}

/* SYSCALL 10: 起動からの基準時刻（unix epoch 秒）を取得。
 * エミュレータが R8 に時刻を返すので R0 へコピーして返す。 */
int os_get_basetime() {
    asm("SYSCALL 10");
    asm("MOV     R0, R8");
}

/* SYSCALL 11: basetime を起点とした現在日時を整形表示。 */
int os_print_date(int basetime) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("SYSCALL 11");
    return 0;
}

/* SYSCALL 20: 全レジスタダンプ（デバッグ用）。 */
int os_regdump() {
    asm("SYSCALL 20");
    return 0;
}

/* SYSCALL 21: dir/ 以下の利用可能プログラム一覧を表示。 */
int os_ls() {
    asm("SYSCALL 21");
    return 0;
}

/* SYSCALL 22: dir/<name>.bin を現タスク上に同期実行（exec 相当）。 */
int os_exec(char *name) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("SYSCALL 22");
    return 0;
}

/* SYSCALL 23: dir/<name>.bin を指定 tid のタスクとして非同期起動。
 * 起動先 tid は呼び出し前に task_find_free_tid で確保しておく。 */
int os_taskexec(int tid, char *name) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("MOV     R9, R7");
    asm("ADDI    R9, 12");
    asm("LDD     R9, [R9]");
    asm("SYSCALL 23");
    return 0;
}

/* key_input (0xB3000) を呼び、入力されたキーコード（R8）を R0 で返す。
 * key_input 内部でキューが空ならタスクスイッチして待つ。 */
int os_key_input() {
    asm("CALLI   key_input");
    asm("MOV     R0, R8");
}

/* CPU を停止して以後の命令実行を止める。OS 終了時に呼ぶ。 */
int os_halt() {
    asm("HALT");
}

/* OS のコマンドプロンプトループ（タスク 0 で動く）。
 * keybuffer (0xC0000) に 1 行入力を組み立て、空白で区切った最初のトークンを
 * 内蔵コマンド（exit / reg / ls / exec / taskexec / date）と突き合わせる。
 * 一致しなければ "Command ... not found." を表示。exit のみループを抜けて HALT。
 * 入力中の特殊キー: BS(8) / DEL(127)=1 文字削除、LF(10)/CR(13)=入力確定、
 * '\\'(92)=エスケープとして読み飛ばし、80 字を超える入力はそれ以上受け付けない。 */
int os_cmdloop_c() {
    char *keybuf;
    char *token;
    int len;
    int ch;
    int tid;
    int basetime;

    keybuf = 0xC0000;
    basetime = os_get_basetime();

    while (1) {
        len = 0;
        keybuf[0] = 0;
        while (1) {
            os_print_string("\x1b[2K\r> ");
            os_print_string(keybuf);
            ch = os_key_input();
            if (ch == 92) {
                continue;
            }
            if (ch == 8 || ch == 127) {
                if (len > 0) {
                    len--;
                    keybuf[len] = 0;
                }
                continue;
            }
            if (ch == 10 || ch == 13) {
                break;
            }
            if (len < 80) {
                keybuf[len] = ch;
                len++;
                keybuf[len] = 0;
            }
        }

        os_print_char(10);
        if (len == 0) {
            continue;
        }

        token = get_nth_token_c(1, keybuf);
        if (cmp_str_c(token, "exit") == 0) {
            os_print_string("bye.\n\n");
            os_halt();
        }
        if (cmp_str_c(token, "reg") == 0) {
            os_regdump();
            continue;
        }
        if (cmp_str_c(token, "ls") == 0) {
            os_ls();
            continue;
        }
        if (cmp_str_c(token, "exec") == 0) {
            token = get_nth_token_c(2, keybuf);
            os_exec(token);
            continue;
        }
        if (cmp_str_c(token, "taskexec") == 0) {
            token = get_nth_token_c(2, keybuf);
            tid = task_find_free_tid();
            if (tid == 0) {
                os_print_string("Could not assign tid.\n");
                continue;
            }
            os_taskexec(tid, token);
            task_mark_runnable(tid);
            continue;
        }
        if (cmp_str_c(token, "date") == 0) {
            os_print_date(basetime);
            continue;
        }

        os_print_string("Command ");
        os_print_string(keybuf);
        os_print_string(" not found.\n");
    }
}

/* sleep (0xB2000) — 引数 R8 = 秒数で呼ばれる。
 * syscall_sleep_prepare_c で task_status を WAITING にしたあと、
 * 戻り先 PC (_sleep_end) と CR を退避して割込禁止下で _task_switch する。
 * 復帰時は _sleep_end から RET し、呼び出し元 (sleep ユーザ) に戻る。 */
asm(".ADDR 0xB2000\nsleep:\n        PUSH    R0\n        PUSH    R1\n        PUSH    R8\n        CALLI   syscall_sleep_prepare_c\n        ADDI    SP, 4\n        POP     R1\n        POP     R0\n        MOVI    R8, _sleep_end\n        PUSH    R8\n        PUSH    CR\n        DI\n        JPI     _task_switch\n_sleep_end:\n        RET");

/* key_input (0xB3000) — キー入力を 1 文字取得。
 * SYSCALL 3 でキューを覗き、空 (R8=0) ならタスクスイッチして待ち、戻ってきて
 * から再度 SYSCALL 3。文字を得るまで yield をループする。
 * 戻り値: R8 にキーコード（呼び出し側でそのまま使う）。 */
asm(".ADDR 0xB3000\nkey_input:\n        SYSCALL 3\n        SBTI    R8, 0\n        JPNZI   _got_key\n_do_yield:\n        MOVI    R8, _resume_point\n        PUSH    R8\n        PUSH    CR\n        DI\n        JPI     _task_switch\n_resume_point:\n        SYSCALL 3\n        SBTI    R8, 0\n        JPZI    _do_yield\n_got_key:\n        RET");

/* task_exit (0xB4000) — タスクの自発終了点。ユーザプログラムの末尾から
 * 呼ばれる（return 後の戻り先として PC に積まれている）。
 * syscall_task_exit_prepare_c が 1 を返したら （tid 1〜3 を NOT_IN_USE 化済み）、
 * 自身の戻り先を task_exit 自身にセットし直してから _task_switch する。
 * 0 を返したら tid=0/4 なので通常 RET。 */
asm(".ADDR 0xB4000\ntask_exit:\n        PUSH    R0\n        PUSH    R1\n        PUSH    R2\n        CALLI   syscall_task_exit_prepare_c\n        SBTI    R0, 0\n        JPZI    _task_exit_end_t0t4\n_task_exit_end:\n        POP     R2\n        POP     R1\n        POP     R0\n        MOVI    R2, task_exit\n        PUSH    R2\n        MOVI    R2, 0\n        PUSH    R2\n        PUSH    CR\n        JPI     _task_switch\n_task_exit_end_t0t4:\n        POP     R2\n        POP     R1\n        POP     R0\n        RET");

asm(".ADDR 0xB5000");

/* os_label_* シリーズ: os.asm 側で定義されているラベルのアドレスを
 * R0 に置くだけ。ccgen.py が inline-asm builtin として検出し、
 * 呼び出し側で CALLI/RET を介さず MOVI 1 命令に展開する。
 * 戻り型は int だが実際にはアドレス（ポインタ）として使う。 */
int os_label_current_task() {
    asm("MOVI    R0, current_task");
}

int os_label_task_status() {
    asm("MOVI    R0, task_status");
}

int os_label_task_sleep_ticks() {
    asm("MOVI    R0, task_sleep_ticks");
}

int os_label_t1_sp() {
    asm("MOVI    R0, _t1_sp");
}

int os_label_t2_sp() {
    asm("MOVI    R0, _t2_sp");
}

int os_label_t3_sp() {
    asm("MOVI    R0, _t3_sp");
}

/* タスク状態配列 (task_status) を tid=1,2,3 の順に走査し、
 * NOT_IN_USE (=2) になっている最初の tid を返す。空きがなければ 0。
 * 戻り値: 1〜3 (空き tid) または 0 (空きなし)。 */
int task_find_free_tid() {
    char *status;
    int tid;

    status = os_label_task_status();
    tid = 1;
    while (tid < 4) {
        if (status[tid] == 2) {
            return tid;
        }
        tid++;
    }
    return 0;
}

/* 指定 tid のタスク状態を RUNNABLE (=0) に設定。taskexec で
 * バイナリをロードしたあと、スケジューラに拾わせるために呼ぶ。 */
int task_mark_runnable(int tid) {
    char *status;

    status = os_label_task_status();
    status[tid] = 0;
    return 0;
}

/* タイマー割込み (int_timer) から呼ばれる sleep カウントダウン処理。
 * task_sleep_ticks[tid*2..tid*2+1] に big-endian で残り 10ms 単位カウントが
 * 入っている。各タスクのカウントを 1 減らし、0 になったら RUNNABLE へ戻す。
 * tid 0〜3 の 4 タスクを毎ティック走査する。 */
int task_update_sleepers_c() {
    char *ticks_base;
    char *status;
    int tid;
    int off;
    int ticks;

    ticks_base = os_label_task_sleep_ticks();
    status = os_label_task_status();
    tid = 0;
    while (tid < 4) {
        off = tid * 2;
        ticks = ticks_base[off] * 0x100 + ticks_base[off + 1];
        if (ticks != 0) {
            ticks--;
            ticks_base[off] = ticks / 0x100;
            ticks_base[off + 1] = ticks % 0x100;
            if (ticks == 0) {
                status[tid] = 0;
            }
        }
        tid++;
    }
    return 0;
}

/* ラウンドロビン式スケジューラの次タスク選択。現タスクの次から始めて
 * 最初に見つかった RUNNABLE (=0) タスクの tid を返す。
 * 全タスクが RUNNABLE でなければ idle タスクの tid=4 を返す。
 * 戻り値: 0〜3 (次に走らせる tid) または 4 (idle)。 */
int scheduler_select_next_task_c() {
    char *current_task_ptr;
    char *status;
    int cand;
    int searched;

    current_task_ptr = os_label_current_task();
    status = os_label_task_status();
    cand = (*current_task_ptr + 1) % 4;
    searched = 0;
    while (status[cand] != 0) {
        searched++;
        if (searched >= 4) {
            return 4;
        }
        cand = (cand + 1) % 4;
    }
    return cand;
}

/* SYSCALL の sleep ハンドラ前処理。現タスクの task_status を WAITING (=1) に
 * 移し、task_sleep_ticks に「ticks * 10」を big-endian で書き込む。
 * 引数 ticks は秒単位、内部カウントは 10ms 単位なので 10 倍する。
 * 呼び出し元（asm 側 sleep 関数）はこの後 _task_switch にジャンプする。 */
int syscall_sleep_prepare_c(int ticks) {
    char *current_task_ptr;
    char *ticks_base;
    char *status;
    int tid;
    int off;
    int sleep_ticks;

    current_task_ptr = os_label_current_task();
    ticks_base = os_label_task_sleep_ticks();
    status = os_label_task_status();
    tid = *current_task_ptr;
    off = tid * 2;
    sleep_ticks = ticks * 10;
    ticks_base[off] = sleep_ticks / 0x100;
    ticks_base[off + 1] = sleep_ticks % 0x100;
    status[tid] = 1;
    return 0;
}

/* task_exit ハンドラ前処理。現タスク (tid=1〜3) を NOT_IN_USE (=2) に戻し、
 * そのタスクのスタックポインタ保存スロットを初期値に再設定する。
 * tid=0 (OS 本体) と tid=4 (idle) は終了対象外。
 * 戻り値: 1 = 終了処理を実施した（asm 側で _task_switch する）、
 *         0 = tid=0/4 のため何もしなかった（呼び出し元はそのまま RET）。 */
int syscall_task_exit_prepare_c() {
    char *current_task_ptr;
    char *status;
    int *sp;
    int tid;

    current_task_ptr = os_label_current_task();
    status = os_label_task_status();
    tid = *current_task_ptr;
    if (tid == 0 || tid == 4) {
        return 0;
    }

    status[tid] = 2;
    if (tid == 1) {
        sp = os_label_t1_sp();
        *sp = 0xF0000;
    } else {
        if (tid == 2) {
            sp = os_label_t2_sp();
            *sp = 0xE8000;
        } else {
            sp = os_label_t3_sp();
            *sp = 0xE0000;
        }
    }
    return 1;
}

/* ページフォルトハンドラ (int_pagefault) から呼ばれるデマンドページング処理。
 * 物理ページ 0〜15 を線形に走査し、ページテーブル全体（0xFFF00〜+0x40 バイト）
 * で未使用な物理ページを見つけ、現タスクの「論理ページ logical_page」を
 * その物理ページに対応付ける（page_table[tid*0x10 + logical_page] = phys）。
 * 引数: logical_page — フォルトを起こした論理ページ番号 (0〜15)
 * 戻り値: 常に 0（物理ページが枯渇した場合はエラーメッセージを出して HALT）。 */
int vm_alloc_page_for_fault_c(int logical_page) {
    char *current_task_ptr;
    char *page_table;
    int physical_page;
    int index;
    int used;
    int tid;

    current_task_ptr = os_label_current_task();
    page_table = 0xFFF00;
    physical_page = 0;
    while (physical_page < 0x10) {
        used = 0;
        index = 0;
        while (index < 0x40) {
            if (page_table[index] == physical_page) {
                used = 1;
                break;
            }
            index++;
        }
        if (!used) {
            tid = *current_task_ptr;
            page_table[tid * 0x10 + logical_page] = physical_page;
            return 0;
        }
        physical_page++;
    }

    os_print_string("Can't allocate physical page.\n");
    os_halt();
    return 0;
}

/* C 言語のお作法上のダミー entry point。本 OS の実エントリは os.asm 側の
 * 起動ルーチン経由で os_cmdloop_c() であり、main は呼ばれない。 */
int main() {
    return 0;
}
