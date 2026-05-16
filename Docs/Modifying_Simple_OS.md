# Simple OS in C — 改修ガイド

`simple_os.c` を起点に Simple OS を改造（機能追加・削除・差し替え）する際の注意点をまとめる。書籍の独自 CPU・独自アセンブラ・独自カーネル ABI という特殊環境のため、汎用 OS の知識だけでは見落とす制約がいくつかある。

このドキュメントは「方針」より「具体的な落とし穴」に重点を置く。設計思想は `Simple_os_plan.md`、コンパイラ仕様は `Simple_C.md` を参照。

---

## 1. 改修前に必ず確認すべき構造的制約

### 1.1 `os.asm` には触れない

派生作業のポリシーとして、書籍著者のオリジナル `os.asm` は読み取り専用ベースラインとして扱う。詳細は `Simple_os_plan.md` の「`os.asm` 無改変ポリシー」節。

C 側 (`simple_os.c`) で表現できないロジックを追加したい場合の選択肢：

1. **可能なら `simple_os.c` 内の `asm()` ブロックで完結させる**（最も推奨）
2. ハイブリッド合成スクリプト `tools/build_simple_os_hybrid.py` を拡張して新しい差し替え範囲を導入（中程度のコスト）
3. `os.asm` 改変（**原則禁止**。どうしても必要な場合は別ファイル `os_ext.asm` 等にして追加合成を検討）

### 1.2 公開 ABI アドレスは動かさない

ユーザープログラム（`dir/*.bin`）は以下の絶対アドレスで OS 関数を呼ぶ。これらは契約であり、変えてはならない：

```
0xB0000 cmp_str
0xB1000 get_nth_token
0xB2000 sleep
0xB3000 key_input
0xB4000 task_exit
0xC0000 keybuffer
0xC1000 tokenbuffer
0xFF800 vector_table
```

C helper 群（0xB5000 以降）は配置範囲が決まっているだけで個別アドレスは自由に変動する。`tools/check_simple_os_labels.py` の `EXPECTED` と `RANGED` 辞書がこの不変条件を検査する。改修後にこのチェックが通ることを必ず確認する。

### 1.3 メモリーマップを破壊しない

| 領域 | 用途 |
|---|---|
| `0x80000`〜 | OS コード |
| `0xB0000`〜`0xBFFFF` | 公開システム関数 (固定アドレス) + C helper 群 |
| `0xC0000` | keybuffer |
| `0xC1000` | tokenbuffer |
| `0xE0000`〜`0xF0000` 周辺 | タスクスタック (T1/T2/T3) |
| `0xFF800` | ベクターテーブル |
| `0xFFF00`〜`0xFFF40` | タスク 0〜3 用ページテーブル (各 16 バイト) |

これらは絶対アドレスで参照されているため、領域の追加や移動は `os.asm` の修正なしには不可能。**新規データ領域が必要な場合、原則として `0xB5000`〜`0xC0000` の C helper 領域の隙間か、未使用な高位アドレスを使う**。

---

## 2. パターン別ガイド

### 2.1 新しいユーザーコマンドを追加する

例：`echo` コマンドを追加するケース。

**変更箇所：** `simple_os.c` の `os_cmdloop_c()` のみ。

```c
if (cmp_str_c(token, "echo") == 0) {
    token = get_nth_token_c(2, keybuf);
    os_print_string(token);
    os_print_char(10);
    continue;
}
```

**注意点：**

- `cmp_str_c` の戻り値は **0 が一致**。逆に思いやすい
- 引数を取るコマンドは `get_nth_token_c(2, keybuf)` で 2 番目以降を取得
- `tokenbuffer (0xC1000)` は `get_nth_token_c` を呼ぶたびに上書きされる。複数のトークンを同時に保持したいなら、`get_nth_token_c` 後すぐに別バッファへコピーする
- ループの末尾 `continue` を忘れると「Command ... not found.」も同時に出る

ビルド：`python tools/build_simple_os.py` のみ。手動で os.asm 等を弄る必要はない。

### 2.2 新しいシステムコール (SYSCALL) を追加する

例：syscall 50 を追加するケース。

**変更箇所：**

1. `emu.py` の `do_syscall(num)` に分岐を追加（C 側からは見えない動作）
2. `simple_os.c` に薄いラッパ関数を追加

**注意点：**

- 引数は **R8、R9 の 2 つまで**（ABI 上の制約）
- 戻り値はエミュレータ側から R8（または R0）に書き込まれる慣例
- 既存番号と重複させない (0〜3, 10〜11, 20〜23, 30, 40〜41 は使用済み — `OriginalCPU.md` 参照)
- 新 syscall を呼ぶ既存のユーザープログラムが古い `os.bin` で動くと未定義動作になる。リビルドが必須

C 側ラッパの例：

```c
int os_my_syscall(int arg) {
    asm("MOV     R8, R7");
    asm("ADDI    R8, 8");
    asm("LDD     R8, [R8]");
    asm("SYSCALL 50");
    return 0;
}
```

### 2.3 新しい C 関数を `0xB5000` 領域に追加する

通常の C 関数定義として書けば自動的に 0xB5000 以降に配置される。

**注意点：**

- **`check_simple_os_labels.py` の `RANGED` 辞書に追加**するのが鉄則。追加せずとも動くが、領域からはみ出した場合に検出できなくなる
- 関数が他の関数から **絶対アドレスで** 呼ばれる必要がある場合（os.asm 側からなど）は、追加で固定アドレスに置く工夫が必要 → 2.4 参照
- 関数本体が単一の `asm("...")` だけかつ引数がゼロの場合、**ccgen.py が inline-asm builtin として自動的に展開する**（CALLI/RET を介さない）。意図しない関数が inline されないよう、複数の文を含めるか引数を取らせるかでパターンを崩す

### 2.4 固定アドレスに新しい公開関数を置く

ユーザープログラムから絶対アドレスで呼びたい関数（例：新しい IPC エントリポイント）を追加する場合。

**変更箇所：** `simple_os.c` に `asm(".ADDR 0xB6000\nmy_entry:\n...");` 形式で配置宣言を追加。

**注意点：**

- `.ADDR` は **前方参照禁止・現在位置より戻る指定不可**。既存の最後の `.ADDR 0xB5000` より大きい値を選ぶ
- 既存の 0xB5000 領域（C helper 群）が 0xB6000 を超えないか `check_simple_os_labels.py` でレンジ確認する。超える場合は新エントリのアドレスを 0xB7000 などに移す
- ユーザープログラム側からは `.DEF my_entry 0xB6000` のような形で参照する慣例

### 2.5 新しいタスクを追加する

書籍の Simple OS はタスク 0〜4 の 5 タスク構成（0=OS、1〜3=ユーザー、4=idle）で**ハードコード**されている。タスク 5 以上を追加する場合：

**変更が必要な箇所：**

- `os.asm` の `task_status`、`task_sleep_ticks`、`_t1_sp`/`_t2_sp`/`_t3_sp` などの配列サイズ
- `os.asm` のページテーブル基点 (`0xFFF00`〜) の容量
- `os.asm` のタスクスタック領域 `T0_STACK_BTM`〜`T4_STACK_BTM` の `.DEF` を拡張
- `simple_os.c` の `task_find_free_tid()` のループ上限 (`tid < 4`)
- `simple_os.c` の `task_update_sleepers_c()` と `scheduler_select_next_task_c()` のループ上限

**注意：これは `os.asm` 無改変ポリシーに違反する**。タスク数拡張は派生作品としての構造を崩す重大変更なので、慎重に判断すること。

### 2.6 新しい割込みハンドラを追加する

書籍のベクターテーブル `0xFF800` は 4 エントリ固定（timer / other / other / pagefault）。新規ハンドラを追加するには `os.asm` の VT 配置の変更が必要 → **原則禁止**。

既存の 4 つの中身を差し替えるなら、`os.asm` の `int_timer` / `int_pagefault` 内に `CALLI` で C 関数を呼ばせる流れが現実的。これも合成スクリプト `build_simple_os_hybrid.py` を拡張する必要があり、コストが高い。

---

## 3. 機能を削除・簡略化するときの注意

### 3.1 公開 ABI ラベルを消してはいけない

`cmp_str` / `get_nth_token` / `sleep` / `key_input` / `task_exit` は **ユーザープログラム側が絶対アドレスで呼ぶ**ため、これらが消えると `dir/` 配下の既存バイナリが動かなくなる。簡略化したい場合は中身を空実装にしても構わないが、ラベルとアドレスは残す。

### 3.2 削除する関数が他の C 関数から呼ばれていないか確認

Simple C はリンカ的なシンボル未定義検出が弱い。削除した関数を別の関数から `CALLI` で呼ぶ asm が残っていると、ビルドは通って実行時に未定義アドレスへジャンプする。`grep -n "<func_name>" simple_os.c os.asm` で参照を必ず洗う。

### 3.3 `_c` サフィックス関数を削除するには両側を消す

公開 ABI 関数（`cmp_str` 等）は asm のラッパ ＋ `_c` サフィックスの C 本体のペアで構成されている。本体だけ消すとラッパからの `CALLI` が宙ぶらりんになる。両方同時に消す。

---

## 4. パフォーマンス上の落とし穴

### 4.1 ローカル変数アクセスは 3 命令コスト

現 ISA に `[base+imm]` アドレッシングがないため、ローカル変数 1 アクセスは：

```
MOV     Rx, R7        ; フレームポインタコピー
SUBI    Rx, N         ; またはADDI Rx, N
LDD/STD R?, [Rx]
```

つまり **ループの内側で頻繁にローカル変数を読み書きすると重い**。書き換えしないループ不変な値はループ外で読んで一旦どこかに置く、配列インデックスをポインタに変換する等の工夫で軽量化可能（ただしレジスタ数が R0〜R9 と限られているので過剰な手動最適化は逆効果）。

### 4.2 即値の 20bit 制限

`MOVI` の即値は 20bit (`0x00000`〜`0xFFFFF`) まで。これを超える定数は ccgen が自動で：

```
MOVI    R0, hi          ; 上位 12 bit
MULI    R0, 0x100000
ORI     R0, lo          ; 下位 20 bit
```

の 3 命令に合成する。アドレス定数（0xFFF00 等）はこのコストを払っている。ループの中で書かないこと。

### 4.3 関数呼び出しのオーバーヘッド

呼び出し側は引数を逆順 PUSH、`CALLI`、戻り後 `ADDI SP, N`。被呼び出し側は `PUSH R7`、`MOV R7, SP`、ボディ、`MOV SP, R7`、`POP R7`、`RET`。**1 回の関数呼び出しで両側合わせて最低 6 命令前後**のオーバーヘッド。ホットパスにある小関数は呼び出し側で展開するか、`inline-asm builtin` パターン（ゼロ引数 + 単一 `asm()` 本体）に揃える。

### 4.4 タスクスイッチのレイテンシ

タスクスイッチは PC・CR・R0〜R9・PT・VT をスタック退避する。1 回のスイッチで **20 命令以上**消費する。`TIMESLICE`（`os.asm` 内の `.DEF`）を不用意に小さくしないこと。

---

## 5. デバッグの足掛かり

### 5.1 ビルドが通らない

| エラー兆候 | 典型的な原因 |
|---|---|
| `cc.py` がパースエラー | Simple C の文法外（`for(;;)`、`switch` 等）。`Simple_C.md` で仕様確認 |
| `asm.py` が "未定義ラベル" | C 関数を消した／改名したのに `os.asm` 側が古い名前で呼んでいる |
| `check_simple_os_labels.py` が FAIL | C helper が領域からはみ出した、または公開 ABI アドレスがずれた |
| `build_simple_os_hybrid.py` が "marker not found" | `os.asm` のランドマーク文字列が見つからない。書籍著者が `os.asm` を更新した可能性 |

### 5.2 実行時に怪しい

- `os_regdump()` （`reg` コマンド）で全レジスタダンプ
- `os.asm` の `int_pagefault` 内で SYSCALL 41 を呼べば、フォルト発生時の論理アドレスが取れる
- `emu.py` の `do_syscall` に `print()` を仕込むのが最速。書籍付属コードに副作用はあるが、ローカル開発では問題なし

### 5.3 検証スイート

改修後は必ず以下が PASS することを確認：

```
python tools/build_simple_os.py            # ビルド + ABI 検査
python tools/os_run.py                     # OS 全体動作 smoke (11 ステップ)
for c in samples/*.c; do
    python cc.py "$c" && python asm.py "${c%.c}.asm" && python test_run.py "${c%.c}.bin"
done                                       # サンプル 28 件
```

このどれかが落ちたら、変更を巻き戻して二分探索的に絞り込むのが速い。

---

## 6. 参考

- `Simple_os_plan.md` — 設計方針と移行計画の全体像
- `Simple_C.md` / `Simple_C.en.md` — Simple C コンパイラの言語仕様
- `OriginalCPU.md` — 独自 32 ビット CPU の命令セット、メモリーレイアウト、SYSCALL 一覧などのオリジナル仕様
- `os.asm` — 書籍著者によるオリジナル実装（読み取り基準）
