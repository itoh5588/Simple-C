# Simple OS — C 化作業計画

Simple OS を、Day1 で作成した Unix V6 風コンパイラ（Simple C）を使って段階的に C に書き直すための作業計画。

## 目的

- `os.asm` を一括で置き換えず、関数単位で C 実装へ移行し、Simple OS を段階的に C に書き直す。
- 既存の `asm.py` / `emu.py` / `os.asm` の仕様を壊さず、旧 OS と同じ挙動を保つ。
- C で書けるロジックを増やし、割込み・コンテキストスイッチ・特殊レジスタ操作だけを asm に残す。

## 前提

- C コンパイラは `cc.py`、`cclex.py`、`ccparse.py`、`ccgen.py`、`ccpre.py` で構成される。
- この C コンパイラを Simple C と呼ぶ。仕様と実装背景は日本語版 `Docs/Simple_C.md` を参照。英語概要は `Docs/Simple_C.en.md` に置く。
- C の呼出規約は、引数をスタック渡し、戻り値を R0、フレームポインタを R7 とする。
- `os.asm` の OS 本体は `0x80000` から始まり、システム関数は `0xB0000` 以降の固定アドレスに置かれている。
- ユーザープログラムは既存の固定アドレスシステム関数を呼ぶ可能性があるため、`cmp_str`、`get_nth_token`、`sleep`、`key_input`、`task_exit` の公開アドレスは維持する。

## 最初に確認するファイル

1. `Docs/OriginalCPU.md`
2. `PLAN.md`
3. `Docs/Day1_2026-05-14.md`
4. `os.asm`
5. `cclib/runtime.asm`
6. `ccgen.py`
7. `asm.py`

## Phase 8-0: 着手前の小整備

### 8-0-1. `asm(".ADDR ...")` の可否確認

目的: C ソース内の `asm()` から `.ADDR` を挿入できるか確認する。

手順:

1. 最小 C ファイルに `asm(".ADDR 0xB0000");` とラベル付き関数を置く。
2. `python cc.py sample.c` で asm を生成する。
3. `python asm.py sample.asm` でアセンブルできるか確認する。
4. 生成されたラベルアドレスが意図通りか確認する。

判断:

- 通る場合: まずは `asm(".ADDR ...")` を配置制御に使う。
- 通らない場合: `cc.py` / `ccgen.py` に section または pragma 相当の機能を追加する。

### 8-0-2. `sizeof` の実装

目的: `struct`、配列、タスク管理領域のサイズ計算を C 側で書きやすくする。

方針:

- `sizeof(int)`、`sizeof(char)`、`sizeof(pointer)`、`sizeof(array)`、`sizeof(struct)` を定数式として扱う。
- 既存の `ccgen.py` の `_var_size`、`_member_size`、`_elem_size` と意味を揃える。
- まずは実行時式ではなく、パース時またはコード生成時に整数リテラルへ畳み込む。

### 8-0-3. グローバル配列初期化子

目的: ベクターテーブル、タスク状態配列、固定データを C 側へ寄せる準備をする。

最小対応:

- `int a[] = {1, 2, 3};`
- `char s[] = "abc";`
- グローバル変数のみ対応でよい。

後回しでよいもの:

- ローカル配列初期化子
- ネストした struct 初期化子
- 指定初期化子

### 8-0-4. ビット演算子

目的: CR、PT、VT、ページテーブル、フラグ操作を C で書ける範囲を増やす。

対応候補:

- `&`
- `|`
- `^`
- `~`
- `<<`
- `>>`

注意:

- `AND`、`OR`、`XOR`、`NOT` は ISA にある。
- シフト命令が無い場合、`<<` は `MULI`、`>>` は `DIVI` による 2 の冪乗限定でもよい。
- OS C 化に必要な演算だけを先に実装する。

## Phase 8-1: OS C 化の土台作成

### 作成候補ファイル

- `os.c`: C 化した OS 本体の入口。
- `os_bindings.asm`: C から呼ぶ低レベル asm ラッパー。
- `cclib/os_runtime.asm`: OS 内部用のランタイム。ユーザープログラム用 `cclib/runtime.asm` と分ける。
- `os_run.py`: OS 全体ロード用の検証 runner。必要になった時点で追加する。

### 低レベル asm に残すもの

- `int_timer`
- `int_pagefault`
- `int_other`
- `_task_switch`
- `IRET`
- `EI` / `DI`
- `CR` / `PT` / `VT` の直接操作
- タスク切替時の R0-R9、PT、VT、CR、PC の退避復元

### C から呼ぶ asm ラッパー候補

- [ ] `enable_interrupt()`
- [ ] `disable_interrupt()`
- [ ] `set_vector_table(addr)`
- [ ] `set_page_table(addr)`
- [ ] `set_control_register(value)`
- [ ] `get_control_register()`
- [x] `os_print_char(c)`
- [x] `os_print_string(s)`
- [ ] `sys_print_int(value, fmt)`
- [x] `os_key_input()`
- [x] `os_ls()`
- [x] `os_exec(name)`
- [x] `os_taskexec(tid, name)`
- [ ] `sys_get_pagefault_addr()`
- [ ] `notify_current_task(tid)`
- [x] `os_regdump()`
- [x] `os_print_date(basetime)`
- [x] `os_get_basetime()`
- [x] `os_halt()`

## Phase 8-2: 低リスク関数から移行

最初に C 化する対象:

1. `cmp_str`
2. `get_nth_token`
3. コマンド文字列定数
4. コマンド判定ロジックの一部

進捗:

- [x] `cmp_str` の C 本体 `cmp_str_c` を追加。
- [x] `get_nth_token` の C 本体 `get_nth_token_c` を追加。
- [x] 固定アドレス公開ラベル `cmp_str` = `0xB0000`、`get_nth_token` = `0xB1000` を asm wrapper で生成。
- [x] 通常 ABI の C ロジックは `samples/test_os_string_funcs.c` で確認。
- [x] 既存 `os.asm` を直接編集せず、`simple_os_hybrid.asm` として統合。
- [x] `python emu.py` 上で OS コマンドループ確認。
- [x] `ls`、`exec hello.bin`、`taskexec hello.bin` を確認。
- [x] `cmdloop` 周辺の C 化。

理由:

- 割込みやタスク切替に直接触れない。
- 入出力が限定されており、旧実装との比較がしやすい。
- `0xB0000` 以降の固定アドレス関数として切り出しやすい。

確認:

- 旧 `cmp_str` と同じ戻り値になること。
- `get_nth_token` が `exec foo`、`taskexec foo 1`、空入力、連続スペースで旧実装と同じ挙動になること。
- ユーザープログラムから固定アドレス経由で呼べること。

## Phase 8-3: コマンドループを C 化

対象:

- `cmdloop`
- `draw_cmdline`
- `keyloop`
- `do_bs`
- `do_enter`
- `do_reg`
- `do_ls`
- `do_exec`
- `do_taskexec`
- `do_date`

方針:

- 最初は既存 asm の制御フローを C へ直訳する。
- きれいな抽象化は後回しにし、旧挙動との一致を優先する。
- `keybuffer` と `tokenbuffer` のアドレスは当面固定アドレスのまま扱う。

確認:

- 起動メッセージが表示される。
- プロンプトが表示される。
- Backspace が効く。
- 未知コマンドで旧エラーメッセージが出る。
- `reg`、`ls`、`date`、`exec`、`taskexec` が旧 OS と同じように呼ばれる。

## Phase 8-4: タスク管理データと選択ロジックを C 化

対象:

- `current_task`
- `task_status[]`
- `task_sleep_ticks[]`
- `task_stack_pointer[]`
- `_sleep_proc`
- `_next_task`
- `_timeslice_proc`
- `_check_timeslice`
- `_find_loop`

方針:

- データ配列は C のグローバルとして置けるか確認する。
- 固定レイアウトが必要な場合は asm 側のラベルを維持する。
- 実際のレジスタ退避復元は asm に残し、次に実行する task id の選択だけ C 化する。

確認:

- タスク0とアイドルタスクの切替が壊れない。
- `sleep` 中のタスクが tick 減算で復帰する。
- `taskexec` で起動したタスク1-3がタイムスライスで切り替わる。

## Phase 8-5: システム関数を C/asm 混在で整理

対象:

- `sleep`
- `key_input`
- `task_exit`

方針:

- 公開アドレスは維持する。
- C で書ける判定や状態更新だけ C 化する。
- SP 保存、resume point、タスク終了後の復帰先調整などは asm を残す。

確認:

- C ユーザープログラムの `sleep()` が動く。
- キー入力待ちタスクが busy loop せず yield する。
- タスク1-3の `task_exit()` が該当タスクだけを終了する。
- タスク0またはタスク4での終了処理が旧実装と一致する。

## Phase 8-6: 割込みとページフォルトの整理

対象:

- `int_timer`
- `int_pagefault`
- `int_other`
- `_task_switch`

方針:

- エントリと出口は asm のままにする。
- ページ割当探索など、純粋なロジックだけ C 関数へ切り出せるか検討する。
- `IRET` 直前のスタック形式は絶対に変えない。

確認:

- タイマー割込みでタスク切替が続く。
- ページフォルトで未割当ページが割り当てられる。
- 物理ページ枯渇時のエラーメッセージが出る。
- フェッチ起因ページフォルト時の PC 補正が旧実装と一致する。

## テスト計画

### コンパイラ単体テスト

既存サンプルを継続確認する。

```sh
python cc.py samples/hello.c
python asm.py samples/hello.asm
python test_run.py samples/hello.bin
```

追加したいサンプル:

- `samples/test_sizeof.c`
- `samples/test_bitops.c`
- `samples/test_global_init.c`
- `samples/test_addr_directive.c`

### OS 比較テスト

1. 旧 `os.asm` を `python asm.py os.asm` でビルドして動作を記録する。
2. C 化版をビルドする。
3. `python emu.py` で起動する。
4. 以下を手動確認する。

確認項目:

- 起動メッセージ
- プロンプト
- `reg`
- `ls`
- `date`
- `exec`
- `taskexec`
- タスク切替
- `sleep`
- ページフォルト
- VC 切替

### 自動 runner 候補

`test_run.py` は単体プログラム用なので、必要になった時点で `os_run.py` を追加する。

`os_run.py` の役割:

- OS バイナリを `0x80000` にロードする。
- ベクターテーブルとページテーブルを初期状態にする。
- テスト用 `dir/` のバイナリを用意する。
- 一定 tick 実行してレジスタ、タスク状態、出力を確認する。

## 完了条件

Phase 8 の最小完了:

- `cmp_str` と `get_nth_token` が C 化され、固定アドレスから呼べる。
- コマンドループの主要部分が C 化される。
- `reg`、`ls`、`date`、`exec`、`taskexec` が旧 OS と同等に動く。
- タイマー割込み、タスク切替、ページフォルトが退行していない。

現状:

- [x] `cmp_str` と `get_nth_token` が C 化され、fixed wrapper から呼べる。
- [x] `cmdloop` は `os_cmdloop_c` へ差し替え済み。
- [x] `reg`、`ls`、`date`、`exec hello.bin`、`taskexec hello.bin`、`exit` を hybrid OS 上で確認。
- [x] ページフォルト退行確認済み。

Phase 8 の理想完了:

- タスク選択ロジックと状態更新が C 化される。
- `sleep`、`key_input`、`task_exit` のロジック部分が C 化される。
- asm に残る範囲が、割込み入口、特殊レジスタ操作、コンテキスト退避復元、`IRET` へ限定される。

## 注意点

- git 管理済みの既存ソースは直接編集しない。`os.asm` は読み取り専用の基準として扱う。
- 既存 OS との差し替え検証は、生成ファイル `simple_os_hybrid.asm` など別名ファイルで行う。
- 既存の公開システム関数アドレスを変えない。
- `os.asm` の挙動比較を常に基準にする。
- C 化のついでに大きな設計変更をしない。
- まず直訳で通し、動作確認後に整理する。
- `asm()` 内のレジスタ使用は C コンパイラの呼出規約と衝突しないようにする。
- R8/R9 は SYSCALL 用かつ caller-saved なので、C 関数境界をまたいで値を保持しない。
- R7 はフレームポインタなので、インライン asm で不用意に壊さない。

## 作業順まとめ

1. `.ADDR` を `asm()` から使えるか検証する。
2. `sizeof`、必要なグローバル配列初期化子、必要なビット演算子を追加する。
3. `cmp_str` と `get_nth_token` を C 化する。
4. コマンドループを C 化する。
5. タスク管理データとタスク選択ロジックを C 化する。
6. `sleep`、`key_input`、`task_exit` を C/asm 混在で整理する。
7. 割込みとページフォルトは最後に最小限だけ整理する。

進捗:

- [x] 1. `.ADDR` を `asm()` から使えるか検証する。
- [x] 2. `sizeof`、必要なグローバル配列初期化子、必要なビット演算子を追加する。
- [x] 3. `cmp_str` と `get_nth_token` を C 化する。
- [x] 4. コマンドループを C 化する。
- [x] 5. タスク管理データとタスク選択ロジックを C 化する。
- [x] 6. `sleep`、`key_input`、`task_exit` を C/asm 混在で整理する。
- [x] 7. 割込みとページフォルトは最後に最小限だけ整理する。

タスク管理の現状:

- `_sleep_proc` は hybrid 生成時に `task_update_sleepers_c` 呼び出しへ差し替え済み。
- `_task_switch` 内の `_find_loop` は `scheduler_select_next_task_c` 呼び出しへ差し替え済み。
- どちらも `task_status` / `task_sleep_ticks` ラベル参照を使うため、`os.asm` 本体内ラベル位置が変わっても追従する。
- `task_update_sleepers_c` と `scheduler_select_next_task_c` の中心ロジックは通常の C ループへ置き換え済み。
- `current_task` / `task_status` / `task_sleep_ticks` など既存 asm ラベルのアドレス取得だけは `os_label_*` helper に閉じ込める。
- 割込み入口、timeslice 判定、SP 保存復元、レジスタ退避復元、`IRET` は asm のまま。

公開関数整理の現状:

- `sleep=0xB2000` は公開 wrapper を生成物側に移し、状態更新を `syscall_sleep_prepare_c` に切り出し済み。
- `key_input=0xB3000` は公開 wrapper を生成物側に移行済み。yield と resume point は asm のまま。
- `task_exit=0xB4000` は公開 wrapper を生成物側に移し、終了対象判定・状態更新・SP 初期化を `syscall_task_exit_prepare_c` に切り出し済み。
- `syscall_sleep_prepare_c` と `syscall_task_exit_prepare_c` の状態更新ロジックは通常の C へ置き換え済み。
- `taskexec sleep.bin` と `taskexec hello.bin` で動作確認済み。

ページフォルトの現状:

- `int_pagefault` のエントリ、PC 補正、退避復元、`IRET` は asm のまま。
- 物理ページ探索とページテーブル更新だけを `vm_alloc_page_for_fault_c` に切り出し済み。
- `vm_alloc_page_for_fault_c` の物理ページ探索とページテーブル更新は通常の C ループへ置き換え済み。
- `taskexec pagefault.bin` で `STDI` / `LDDI` によるページフォルト発生後、`0x12345` を読み戻せることを確認済み。

## Hybrid 生成メモ

既存 `os.asm` を直接編集しない方針のため、`tools/build_simple_os_hybrid.py` で別名の合成 asm を生成する。

入力:

- `os.asm`
- `simple_os.asm`

出力:

- `simple_os_hybrid.asm`

処理:

- `os.asm` の `cmdloop` ブロックを `CALLI os_cmdloop_c` に差し替える。
- `_sleep_proc` を `CALLI task_update_sleepers_c` に差し替える。
- `_task_switch` 内の task 選択ループを `CALLI scheduler_select_next_task_c` に差し替える。
- `int_pagefault` 内のページ割当探索を `CALLI vm_alloc_page_for_fault_c` に差し替える。
- `os.asm` の `.ADDR 0xB0000` から `.ADDR 0xC0000` 直前までを、`simple_os.asm` の生成物に差し替える。

確認済みラベル:

```
cmp_str=0xB0000
cmp_str_c=0xB0038
get_nth_token=0xB1000
get_nth_token_c=0xB1038
sleep=0xB2000
key_input=0xB3000
task_exit=0xB4000
```

## `os.asm` 無改変ポリシー

派生作業を通じて、書籍著者のオリジナル `os.asm` には**一切手を入れない**ことを構造的な制約として守る。

### 方針

- ✅ **読む** — 公開 ABI ラベル、構造、ランドマーク文字列の参照基準として使う
- ❌ **書く** — 上書き・追記・編集は一切しない（小さなコメント追加も含めて行わない）

### 根拠

1. **派生作品としての純度** — 「書籍著者の手書き OS をそのまま土台に残し、その上層を C で書き換えた」という構造が、上流への敬意と派生の独自性を同時に示す。
2. **上流追従の単純さ** — 上流（書籍著者）が `os.asm` を更新した際、こちら側のマージ作業は理論上 `git pull` だけで済む。
3. **責務の分離** — 手書き asm 領域と C 由来領域が物理的に別ファイルに分かれるため、どちらに変更を入れるべきか迷いが生じない。

### 検証

```
git log --oneline -- os.asm
```

すべて書籍著者 SUEYASU 氏のコミット（日本語コミットメッセージ）のみで、派生作業のコミット（伊藤名義の英語タイトル群）は一度も `os.asm` に触れていない。新しい派生コミットを入れる前にこの不変条件を確認すること。

### 依存する暗黙の前提（壊れ得るポイント）

`tools/build_simple_os_hybrid.py` は `os.asm` 内の**文字列ランドマーク**を探して合成位置を決めるため、上流が以下を変更すると合成が失敗する：

| ランドマーク | 用途 |
|---|---|
| `.ADDR 0xb0000` / `.ADDR 0xc0000` | システム関数領域の境界 |
| `cmdloop:` | コマンドループ開始 |
| `; Handler` | コマンドループ終端 |
| `_sleep_proc:` / `_timeslice_proc:` | sleep カウントダウン差し替え範囲 |
| `_save_sp:` / `_select_next:` / `MOVI    R2, 0` | スケジューラ選択差し替え範囲 |
| `DIVI    R8, 0x10000` / `POP     R8` | ページフォルト C 呼び出し挿入点 |

上流で：
- **行追加・微修正**（ABI ラベル位置と上記ランドマーク不変）→ 問題なく追従可能
- **ラベル名変更・領域配置変更・ランドマーク文字列変更** → 合成スクリプトがランドマークを見失って失敗。追従にはスクリプト側の修正が必要。

### 検出

`tools/check_simple_os_labels.py` が公開 ABI ラベル座標と C helper の配置範囲を検証するため、上流変更に追従できなくなった場合は `tools/build_simple_os.py` 実行時に即エラーとなる。サイレントな ABI ずれは原理的に発生しない。

## Build / Check

Phase 8 の標準ビルド:

```
python tools/build_simple_os.py
```

このコマンドで以下を実行する。

- `simple_os.c` のコンパイル
- `simple_os_hybrid.asm` の生成
- `simple_os_hybrid.bin` のアセンブル
- 公開 ABI ラベル検査
- `hello.bin` / `sleep.bin` / `pagefault.bin` の準備
- `emu.py` 用 `os.bin` と `dir/` の準備

公開 ABI ラベル検査のみ:

```
python tools/check_simple_os_labels.py
```

検査対象:

- `cmp_str`
- `get_nth_token`
- `sleep`
- `key_input`
- `task_exit`
- `keybuffer`
- `tokenbuffer`
- `vector_table`
- C 化済み helper が用途別の配置範囲に収まること

現在の検査対象 helper:

- `os_cmdloop_c`: `0xB0000 <= addr < 0xB2000`
- `task_update_sleepers_c`: `0xB5000 <= addr < 0xC0000`
- `scheduler_select_next_task_c`: `0xB5000 <= addr < 0xC0000`
- `syscall_sleep_prepare_c`: `0xB5000 <= addr < 0xC0000`
- `syscall_task_exit_prepare_c`: `0xB5000 <= addr < 0xC0000`
- `vm_alloc_page_for_fault_c`: `0xB5000 <= addr < 0xC0000`

## 最新確認結果

通常の C へ寄せ、責務ベースの関数名へ整理した `simple_os.c` で `python tools/build_simple_os.py` と `python emu.py` を確認済み。

`tools/check_simple_os_labels.py` は、固定 ABI ラベルに加えて C helper の配置範囲も検査する。

確認内容:

- 起動: `Welcome to Simple OS!` とプロンプト表示。
- `ls`: `hello.bin` / `pagefault.bin` / `sleep.bin` を表示。
- `date`: 日時表示。
- 未知コマンド `foobar`: `Command foobar not found.` を表示。
- `exec hello.bin`: `Hello, World!` を表示。
- `taskexec hello.bin`: VC 1 で `Hello, World!` を表示。
- `taskexec sleep.bin`: VC 1 で `WAITING 1s` / `WAITING 5s` / `WAITING 10s` を表示。
- `taskexec pagefault.bin`: VC 2 で `STDI   R0, [0x23000]` / `LDDI   R0, [0x23000]` / `12345` を表示。
- `exit`: `bye.` の後 `CPU halted.`。

## Remaining asm boundary

`simple_os.c` と `tools/build_simple_os_hybrid.py` に残る asm は、現時点では境界処理に限定されている。

### 固定アドレス公開 wrapper

ユーザープログラムや既存 OS ABI から呼ばれる入口。公開アドレス維持が目的なので asm のまま残す。

- `cmp_str=0xB0000`
  - R8/R9 ABI を C ABI に積み替えて `cmp_str_c` を呼ぶ。
  - 戻り値 R0 から Zero flag を作る。
- `get_nth_token=0xB1000`
  - R8/R9 ABI を C ABI に積み替えて `get_nth_token_c` を呼ぶ。
  - 戻り値 R0 を旧 ABI の R8 に戻す。
- `sleep=0xB2000`
  - R8 の sleep 秒数を `syscall_sleep_prepare_c` に渡す。
  - resume point、`PUSH CR`、`DI`、`_task_switch` 接続は asm。
- `key_input=0xB3000`
  - `SYSCALL 3` でキー入力を読む。
  - 入力がなければ resume point を積んで `_task_switch` へ yield する。
- `task_exit=0xB4000`
  - `syscall_task_exit_prepare_c` で状態更新する。
  - task1-3 の終了時だけ `_task_switch` に接続する。

### OS syscall wrapper

C のスタック ABI から既存 `SYSCALL` ABI へ橋渡しする薄い wrapper。

- `os_print_char`
- `os_print_string`
- `os_get_basetime`
- `os_print_date`
- `os_regdump`
- `os_ls`
- `os_exec`
- `os_taskexec`
- `os_key_input`
- `os_halt`

これらは C コンパイラが `SYSCALL` や HALT を直接表現できないため asm のまま残す。

### 既存 asm ラベル取得 helper

`os.asm` 側に残るデータラベルを C ロジックから参照するための境界。

- `os_label_current_task`
- `os_label_task_status`
- `os_label_task_sleep_ticks`
- `os_label_t1_sp`
- `os_label_t2_sp`
- `os_label_t3_sp`

将来的には optimizer / builtin 化で、`CALLI os_label_*` を `MOVI R0, label` に直接展開する候補。

### hybrid 生成スクリプト側の asm 境界

`tools/build_simple_os_hybrid.py` が既存 `os.asm` の低レベル制御を残しつつ、ロジック部分だけ C helper 呼び出しへ差し替える。

- `cmdloop`
  - `CALLI os_cmdloop_c`
  - 起動後のコマンドループ本体を C へ移す入口。
- `_sleep_proc`
  - R0-R3 を退避して `CALLI task_update_sleepers_c`。
  - timer 割込み中の caller-saved 保護が目的。
- `_task_switch` 内の task 選択
  - `CALLI scheduler_select_next_task_c`
  - SP 保存復元、レジスタ退避復元、`IRET` 接続は asm のまま。
- `int_pagefault` 内のページ割当
  - fault address から logical page を作って `CALLI vm_alloc_page_for_fault_c`。
  - 割込み入口、PC 補正、退避復元、`IRET` は asm のまま。

### C 化済みロジック

以下は中心ロジックが通常 C になっており、asm は境界 helper 経由に閉じている。

- `cmp_str_c`
- `get_nth_token_c`
- `os_cmdloop_c`
- `task_find_free_tid`
- `task_mark_runnable`
- `task_update_sleepers_c`
- `scheduler_select_next_task_c`
- `syscall_sleep_prepare_c`
- `syscall_task_exit_prepare_c`
- `vm_alloc_page_for_fault_c`

### 今後の整理候補

- `os_label_*` builtin 化。
- `simple_os.c` の並びを、公開 wrapper / OS syscall wrapper / command loop / label helper / task / scheduler / VM の順に整理する。
- `SYSCALL` wrapper を将来の compiler builtin または専用 runtime に分離する。
- 残 asm が境界処理だけであることを、引き続き `Docs/Simple_os_plan.md` のこの節で管理する。

## Next Task

通常 C 化後のソース配置整理に進む。

優先順:

1. `simple_os.c` の並びを、公開 wrapper / OS syscall wrapper / command loop / label helper / task / scheduler / VM の順へ整理する。
2. 関数順変更後に `python tools/build_simple_os.py` と `python emu.py` で退行確認する。
3. optimizer に入る前に、`os_label_*` builtin 化の設計を決める。
