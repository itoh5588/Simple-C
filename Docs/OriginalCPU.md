# Original CPU / Simple OS リファレンス

書籍『いちばんやさしい！OS自作超入門』（末安 泰三 著、日経BP）の付属コードで使われている**独自 32 ビット CPU の仕様**と、その上で動く **Simple OS のメモリーレイアウト・ABI** をまとめた参照資料。`asm.py`（アセンブラ）と `emu.py`（CPU エミュレータ）の両者が共有する仕様であり、派生作業（Simple C コンパイラ、`simple_os.c` 等）はこの仕様を基底として動く。

書籍著者によるオリジナル仕様の記録なので、派生作業で書き換えてはいけない。CPU 拡張を伴うコード変更を行う際は本文書と `asm.py` / `emu.py` の両方を同期して更新する必要がある（→ `Modifying_Simple_OS.md` 参照）。

## 動作環境

ホスト OS は Linux または macOS のみ（`emu.py` が termios を使用するため）。Windows の場合は WSL を使う。Python 3.8 以降が必要（3.11 以降を推奨）。

## ビルドと実行

```bash
# OSのアセンブル（os.asm → os.bin）
python asm.py os.asm

# OSの起動（カレントディレクトリの os.bin をロード）
python emu.py

# 単体プログラムのアセンブル（拡張子 .asm → .bin に置き換え）
python asm.py hello.asm   # → hello.bin
```

`emu.py` には引数がなく、固定で `os.bin` を読み込む。OS 起動後、`exec` / `taskexec` コマンドで呼び出すユーザープログラムは `dir/` サブディレクトリに配置する必要がある（このディレクトリはリポジトリには含まれていない。利用時に自分で作成する）。

エミュレータ操作中の仮想コンソール切替は `Ctrl+]` に続けて `0`〜`3`。

テストフレームワークやリンタは存在しない。動作確認は実際に OS／プログラムを動かして行う。

## コンポーネント構成

リポジトリは 3 つの層から成る：

1. **asm.py** — アセンブラ。`.asm` を独自 CPU 向けの 32 ビット固定長バイナリにアセンブルする。
2. **emu.py** — CPU エミュレータ。`os.bin` をロードして実行し、システムコール／割り込み／ページングを模擬する。
3. **\*.asm** — アセンブリソース。`os.asm` が OS 本体、その他はユーザープログラム例。

## 独自 CPU の命令セット（asm.py / emu.py で共有）

- 命令長・レジスタ長すべて 32 ビット固定。即値は 20 ビットまで。アドレス幅 20 ビット（1 MiB メモリー空間）。
- 命令を 6 タイプに分類し、第 1 バイト上位 4 ビットでタイプを判別、下位 4 ビットでオペコードを判別する：
  - Type 0（`type0_opdic`）：オペランド無し（NOP, HALT, RET, IRET, EI, DI）
  - Type 1（`type1_opdic`）：単一レジスタまたはレジスタ間接ジャンプ（PUSH, POP, INC, DEC, NOT, JP/CALL/条件分岐）
  - Type 2（`type2_opdic`）：レジスタ間演算（MOV, ADD, SUB, MUL, ... AND/OR/XOR）
  - Type 3（`type3_opdic`）：メモリーアクセス（`LDB R1, [R2]` 形式）
  - Type 4（`type4_opdic`）：即値演算（MOVI, ADDI, ...）
  - Type 5（`type5_opdic`）：絶対アドレス指定メモリーアクセス（LDBI, STBI, ...）
  - Type 6（`type6_opdic`）：即値 SYSCALL／即値ジャンプ
- レジスタ：汎用 R0〜R9、加えて TP（タイマー）、SP、PC、PT（ページテーブルベース）、VT（ベクターテーブルベース）、CR（コントロール／フラグ）。
- CR レジスタの上位ビットは制御フラグ：`0b0100 << 28` = 割り込み許可（EI）、`0b1000 << 28` = MMU 有効。下位は演算結果フラグ（Zero/Overflow/Underflow）。
- 命令テーブルやレジスタ表（`registers_dic`）は `asm.py` と `emu.py` の両方に重複定義されているので、CPU 仕様を拡張する際は両側を変更する。

## アセンブラのディレクティブ（asm.py）

- `.BYTE` / `.WORD` / `.DWORD` — データ埋め込み（1/2/4 バイト）
- `.STRING "..."` — UTF-8 文字列 + NUL 終端
- `.DEF NAME expr` — 定数定義。前方参照は第 2 パス冒頭で反復解決される
- `.ADDR addr` — 位置カウンタの前進（前方参照禁止、現在位置より小さい値はエラー）
- ラベルは `label:` 形式。`;` 以降はコメント（クオート外のみ）。
- 二段階アセンブル：first_pass でラベル収集とレイアウト計算、second_pass で本エンコード。

## Simple OS（os.asm）のメモリーレイアウト

| アドレス | 用途 |
|---------|------|
| `0x80000` | OS コード開始（タスク初期化、コマンドループ、各種ハンドラ） |
| `0xB0000`〜 | システム関数（`cmp_str`、`get_nth_token`、`sleep`、`key_input`、`task_exit`）。それぞれ固定の `.ADDR` で配置されており、ユーザープログラムから絶対アドレスで呼び出せる（例：`hello_task.asm` の `.DEF sleep 0xB2000`） |
| `0xC0000` | `keybuffer`（コマンド入力） |
| `0xC1000` | `tokenbuffer` |
| `0xFF800` | ベクターテーブル（timer / other / other / pagefault） |
| `0xFFF00`〜`0xFFF30` | タスク 0〜3 用ページテーブル（各 16 バイト） |

各タスクのスタックは別領域に分かれている（`T0_STACK_BTM` 〜 `T4_STACK_BTM`、`os.asm` 冒頭の `.DEF` 参照）。

## マルチタスクとページング

- タスク 0 は OS 本体、タスク 1〜3 はユーザータスク（`taskexec` で起動）、タスク 4 はアイドルループ。
- タスク状態は `task_status` 配列（RUNNABLE / WAITING / NOT_IN_USE）。タイマー割り込み（`int_timer`）が `TIMESLICE` 周期で `_task_switch` を呼ぶ。
- コンテキストスイッチでは PC・CR・R0〜R9・PT・VT をスタックに退避し、`task_stack_pointer[tid]` に SP を保存する。
- ページサイズ 64 KiB、論理ページ数 16。MMU 有効時、`get_paddr` がページテーブルを参照してアドレス変換し、未割当（`0xFF`）ならページフォルト例外を投げる。
- ページフォルトハンドラ（`int_pagefault`）は物理ページを線形に探索して割り当てる（デマンドページング）。フォルト発生 PC は原因がフェッチか否かで補正される。
- ユーザープログラムは `dir/<file>` から読み込まれ、論理アドレス `0x00000` にロードされて実行される（タスクごとに別物理ページにマップ）。

## システムコール（emu.py `do_syscall`）

`SYSCALL imm` で呼び出す。引数は R8・R9。代表的なもの：

| 番号 | 機能 |
|------|------|
| 0 | print char (R8) |
| 1 | print string (R8=アドレス) |
| 2 | print int with format (R8=値, R9=fmt 文字列) |
| 3 | get char (ノンブロッキング、空なら `\0`) |
| 10 / 11 | 時刻取得 / 日時表示 |
| 20 | レジスタダンプ |
| 21 / 22 / 23 | ls / exec / taskexec |
| 30 | エミュレータに現タスク ID を通知（VC 切替に使う） |
| 40 | ヘックスダンプ |
| 41 | ページフォルト発生論理アドレスを取得 |

## 仮想コンソール

エミュレータは `mp.Process` で別プロセスを 2 つ起動する（タイマー割り込み、キーボード入力）。キー入力はアクティブ VC のキューに振り分けられ、`current_task_id` に応じて出力先 VC が選ばれる（タスク 0〜3 が同番号の VC に対応）。`Ctrl+]` を受けた次の `0`〜`3` は VC 切替コマンドとして OS には渡らない。
