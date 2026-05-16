# Simple C

Simple C は、Simple OS 実験用の小さな C コンパイラである。

ISO C の完全な実装ではない。Simple OS と、このリポジトリの独自 ISA
向けに作っている、Unix V6 風の実用的なサブセットコンパイラとして扱う。

英語版の概要は `Docs/Simple_C.en.md` に置く。今後の主文書はこの日本語版とする。

## 目的

- Simple OS 上で動く小さなユーザープログラムを C で書けるようにする。
- Simple OS 自体を段階的に C で書けるようにする。
- 実装を読んで理解しやすい形に保つ。
- ユーザープログラムが依存する既存の固定アドレス ABI は壊さない。

## 背景

Simple C は、古典的な小型コンパイラの流れに沿っている。

1. ソースをプリプロセスする。
2. 字句解析で token 列にする。
3. 構文解析で AST を作る。
4. AST からターゲット asm を直接生成する。
5. `asm.py` でバイナリへアセンブルする。

参考になる教科書・資料:

- Brian W. Kernighan, Dennis M. Ritchie『プログラミング言語C 第 2 版』（共立出版）— C 言語側のリファレンス
- 植山類『低レイヤを知りたい人のためのCコンパイラ作成入門』（オンライン公開、日本語）— chibicc を題材にした手書き再帰下降 + 直接 codegen による小型 C コンパイラの解説
- Jack Crenshaw, *Let's Build a Compiler*（オンライン公開、英語）— 手書き再帰下降 + 直接 codegen の古典的チュートリアル

これらは学習背景として挙げている。本文、図、まとまったコード例は転載しない。

## 実装方式

Simple C は意図的に素直な構成にしている。

- `ccpre.py`: 簡易プリプロセッサ
- `cclex.py`: 手書き lexer
- `ccparse.py`: 手書き再帰下降パーサー（recursive descent parser）
- `ccparse.py`: Python `dataclass` による AST ノード定義
- `ccgen.py`: AST から Simple OS asm を直接出力するコード生成器
- `cc.py`: compiler driver
- `cclib/runtime.asm`: ユーザープログラム用 runtime

yacc、bison、ANTLR、parser combinator、外部 parser generator は使っていない。

現時点では独立した IR（中間表現）は無い。`ccgen.py` が AST を直接たどり、ターゲット asm を出す。
optimizer は IR を介さず、AST → asm 生成パスの中と、生成直後の line 列に対する 1 パスの peephole として組み込んでいる。詳細は「Optimizer」節を参照。

## ビルドの流れ

通常のユーザープログラム:

```sh
python cc.py samples/hello.c
python asm.py samples/hello.asm
```

OS 内部用に runtime を付けない場合:

```sh
python cc.py --no-runtime simple_os.c
python asm.py simple_os.asm
```

`cc.py` は `<source>.asm` を出力する。`asm.py` がその asm を `.bin` に変換する。

デフォルトでは `cclib/runtime.asm` を末尾に付ける。`--no-runtime` を指定すると runtime を付けない。
OS 内部コードでは、既存 OS ABI と接続するために `--no-runtime` を使う。

## プリプロセッサ

`ccpre.py` が対応するもの:

- オブジェクト形式の `#define NAME VALUE`
- `#include "file"`
- `#include <file>`

include は、include しているソースファイルのディレクトリを基準に解決する。

制限:

- 関数形式 macro は未対応。
- 条件コンパイルは未対応。
- system include path は無い。
- macro 展開は行単位・文字列ベースの簡易実装。

## コメント

Simple C のソースでは、C の一般的なコメント形式を使える。

```c
// 行コメント

/*
 * ブロックコメント
 */
```

そのため、C ソース先頭に SPDX コメントを書くこともできる。

```c
// SPDX-License-Identifier: MIT
```

ただし、ライセンス全体はルート `LICENSE` と `Docs/LICENSE.md` で管理する。
各ファイルへの SPDX コメント追加は任意とする。

## 字句解析

`cclex.py` は以下を認識する。

- 識別子
- 10進整数リテラル
- 16進整数リテラル
- 文字列リテラル
- 文字リテラル
- 行コメント
- ブロックコメント
- C 風の演算子と記号

文字列・文字リテラルで使える escape:

- `\n`
- `\t`
- `\r`
- `\0`
- `\\`
- `\"`
- `\'`
- `\b`
- `\a`
- `\f`
- `\v`
- `\xNN`

未知の escape は、その文字自身として扱う。

## 構文解析

`ccparse.py` は手書きの再帰下降パーサーである。

AST は `dataclass` ノードで表現する。

- `Function`
- `VarDecl`
- `If`
- `While`
- `For`
- `Return`
- `BinOp`
- `Call`
- `Member`
- `InlineAsm`

式の parser は優先順位ごとに関数を分けている。

1. 代入
2. logical OR
3. logical AND
4. bitwise OR
5. bitwise XOR
6. bitwise AND
7. equality
8. relational
9. shift
10. additive
11. multiplicative
12. unary
13. postfix
14. primary

## 対応している C サブセット

型:

- `int`
- `char`
- pointer
- array
- `struct`

関数:

- 型付き引数の関数定義
- K&R style の引数名 + 後続型宣言
- 戻り値は `int` 相当として扱う

文:

- local declaration
- expression statement
- `return`
- `if` / `else`
- `while`
- `for`
- `break`
- `continue`
- block
- inline `asm("...");`

式:

- integer literal
- string literal
- variable
- 識別子を対象にした function call
- assignment
- unary `+`, `-`, `!`, `~`, `&`, `*`
- variable に対する prefix / postfix `++` / `--`
- array indexing
- struct member access `.`
- pointer member access `->`
- arithmetic `+`, `-`, `*`, `/`, `%`
- comparison `==`, `!=`, `<`, `<=`, `>`, `>=`
- logical `&&`, `||`
- bitwise `&`, `|`, `^`
- shift `<<`, `>>`
- `sizeof(type)` と `sizeof expr`

## 型と storage model

`ccgen.py` は、load / store、pointer scaling、member offset、`sizeof` のために簡単な型情報を持つ。

size model:

- `char`: `sizeof` では 1 byte
- `int`: 4 bytes
- pointer: 4 bytes
- array: 要素サイズ × 要素数
- `struct`: member を packed 配置。struct 内 padding は入れない。

storage model:

- scalar local は 4 byte stack slot を使う。
- local array / struct は 4 byte 境界に丸めて stack frame に置く。
- global `char` は 1 byte。
- global `int` と pointer は `.DWORD`。
- global array は byte 列として出力する。
- struct member は packed 配置。

式中の array と struct は、Unix V6 風に address として扱う。

## ABI

Simple C の関数 ABI:

- 引数は右から左へ stack に push する。
- 戻り値は `R0`。
- `R7` を frame pointer として使う。
- caller-saved: `R0` から `R3`、`R8`、`R9`
- callee-saved by convention: `R4` から `R7`

prologue:

```asm
PUSH    R7
MOV     R7, SP
SUBI    SP, frame_size
```

epilogue:

```asm
MOV     SP, R7
POP     R7
RET
```

## Runtime

`cclib/runtime.asm` は通常ビルドで末尾に付く。

現在提供する関数:

- `putchar(c)`
- `puts(s)`
- `getchar()`
- `printd(n)`
- `printx(n)`
- `exit()`

これらは Simple C の stack ABI と Simple OS の `SYSCALL` ABI を橋渡しする。

## Inline Assembly

Simple C は inline asm を受け付ける。

```c
asm("MOVI    R0, 123");
```

関数内 `asm()` と top-level `asm()` の両方に対応する。

OS を C で書く場合は、top-level `asm()` を固定アドレス配置に使える。

```c
asm(".ADDR 0xB0000");
```

top-level `asm()` がある場合、`ccgen.py` は top-level item を source order で出力する。
top-level `asm()` が無い通常プログラムでは、従来通り `main` を先に出力する。

## OS を C で書くための機能

Simple C には、通常のユーザープログラムだけでなく、Simple OS 自体を C で書くために追加した機能がある。

OS を C で書く時に重要な機能:

- `--no-runtime`
- top-level `asm(".ADDR ...")`
- fixed-address wrapper
- `sizeof`
- global array initializer
- `char[]` の string initializer
- bitwise operator
- shift operator
- pointer arithmetic
- packed struct

一方、低レベル CPU 境界は asm に残す。

- interrupt entry / return
- `IRET`
- `EI` / `DI`
- `CR` / `PT` / `VT`
- task switch の register save / restore
- user-facing fixed ABI entry point

このリポジトリでは、Simple OS を段階的に C に書き直す作業を Phase 8 と呼んでいる。

## Global Initializer

対応例:

```c
int values[] = {1, 2, 3};
char name[] = "abc";
int x = 123;
```

global initializer は compile-time constant に限る。

対応している constant initializer:

- integer literal
- `sizeof`
- unary `-`
- unary `~`
- arithmetic
- bitwise operation
- shift

制限:

- local array initializer は未対応。
- local struct initializer は未対応。
- struct global initializer は未対応。
- nested initializer は未対応。
- designated initializer は未対応。

## Shift

ターゲット ISA には専用 shift 命令が無い。

Simple C は shift を loop で生成する。

- `x << n`: `MULI R0, 2` を n 回
- `x >> n`: `DIVI R0, 2` を n 回

右 shift は signed arithmetic right shift ではなく、division based の unsigned 的な挙動になる。

## 制限事項

現在の主な制限:

- 独立した IR が無い。
- register allocator が無い。
- function pointer は未対応。
- cast は未対応。
- `typedef` は未対応。
- `enum` は未対応。
- `union` は未対応。
- `static` storage behavior は未対応。
- `extern` linker model は未対応。
- `goto` は未対応。
- `do while` は未対応。
- `switch` は未対応。
- variadic function は未対応。
- floating point は未対応。
- 多次元配列 syntax は実用上未整備。
- function call の対象は identifier のみ。
- `++` / `--` は現状 variable のみ。
- pointer subtraction は未対応。
- struct value passing / struct return は未対応。

一部 keyword は token 化だけされていて、構文やコード生成は未実装である。
token として認識されることと、その言語機能が動くことは別として扱う。

## Optimizer

独立した IR を持たないため、optimizer は AST → asm 生成パスの中と、生成直後の line 列に対する 1 パス peephole として実装している。`simple_os.asm` を題材に、3 フェーズに分けて段階的に追加した。

- **第1フェーズ — builtin inline 化**: ゼロ引数で本体が単一 `InlineAsm` の関数を呼び出し側で直接展開（`os_label_*` 6 個と `os_halt` が対象）。`CALL` + プロローグ・エピローグ + `RET` の 7 命令を 1 命令へ。
- **第2フェーズ — peephole + 直接 load + 定数畳み込み**: `JPI` 直後にラベル / 隣接 `PUSH`/`POP` 同レジスタ / 自己 `MOV` の削除、`MOV R1,R0; LDD R0,[R1]` を `LDD R0,[R0]` 1 命令へ、右辺 `IntLit` の二項演算と定数 shift を即値 1 命令へ。
- **第3フェーズ — compare-branch fusion + 短絡評価**: 0/1 マテリアライズなしで `SBT` 結果から直接分岐、比較の右辺 `IntLit` を `SBTI` 1 命令化、`&&` / `||` / `!` を再帰的に直接分岐へ分解（値文脈にも適用）。

`simple_os.asm` の行数で見たサイズ変化:

| 段階 | `simple_os.asm` 行数 | 元との差分 |
|---|---|---|
| 最適化なし | 2223 | — |
| 第1フェーズ後 | 2167 | -56 (-2.5%) |
| 第2フェーズ後 | 1940 | -283 (-12.7%) |
| 第3フェーズ後 | 1561 | -662 (-29.8%) |

将来的には `-O0` / `-O1` / `-O2` / `-Os` のような mode 分けが自然だが、現状はサイズと速度の両方に効きやすい局所最適化のみを常時有効にしている。

## テストと例

よく使う確認コマンド:

```sh
python -m py_compile cc.py cclex.py ccparse.py ccgen.py ccpre.py
for f in samples/*.c; do python cc.py "$f" && python asm.py "${f%.c}.asm"; done
python tools/build_simple_os.py
python tools/check_simple_os_labels.py
```

代表的な sample:

- `samples/hello.c`
- `samples/test_asm.c`
- `samples/test_sizeof.c`
- `samples/test_bitops.c`
- `samples/test_global_init.c`
- `samples/test_addr_directive.c`
- `samples/test_os_string_funcs.c`

## License

Simple C の source code は、各ファイルが別途明記しない限り、repository root の MIT License に従う。

この文書は `Docs/LICENSE.md` に記載した documentation license に従う。
