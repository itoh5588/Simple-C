# Simple C

書籍『いちばんやさしい！OS自作超入門』（末安 泰三 著、日経BP）の独自 32 ビット CPU 向けに書いた、小さな C コンパイラ（K&R スタイルのサブセット）です。応用例として、書籍に付属する **Simple OS** のロジック部分をこの Simple C で書き直した **Simple OS in C** も含みます。

## 構成

| | 内容 |
|---|---|
| **Simple C** | Python で書かれた C コンパイラ（約 2,200 行）。`asm.py` 互換のアセンブリを出力する。`cc.py` がエントリポイント |
| **Simple OS in C** | `examples/os/simple_os.c` ＋ ハイブリッド合成スクリプト群。書籍著者の手書き `os.asm` は無改変で残し、ロジック部のみ C から生成した asm に差し替える |

## 上流依存

このリポジトリは書籍著者の独自 CPU・アセンブラ・OS 実装を土台として動きます。書籍のコードは <https://github.com/sueyasu/os_book_code> から `tools/setup.py` 経由で `vendor/book/` に取得します。本リポジトリには書籍由来のファイルは含まれません。

書籍のコード（MIT License）への敬意と、それを土台にした派生作品としての立場を維持するため、`os.asm` には一切手を入れません（読み取り基準として扱う）。

## 動作環境

- Linux または macOS（`emu.py` が termios を使用するため）
- Windows は WSL2 経由で
- Python 3.8 以降（3.11 以降推奨）

## セットアップ

```bash
git clone https://github.com/itoh5588/Simple-C.git
cd Simple-C
python tools/setup.py
```

`setup.py` の処理：

1. <https://github.com/sueyasu/os_book_code> を `vendor/book/` へ clone（失敗時は自分のミラー `https://github.com/itoh5588/os_book_code` にフォールバック）
2. 動作確認済みのコミット（`5542998`）をチェックアウト
3. `emu.py` に小さなパッチを適用（`\r` 単体を `\n` に変換していたバグの修正。upstream に Issue 報告済み）
4. `asm.py` / `emu.py` / `os.asm` / `sleep.asm` / `pagefault.asm` をリポジトリルートにシンボリックリンクで配置

## ビルドと実行

### Simple OS in C を動かす

```bash
python tools/build_simple_os.py     # コンパイル → ハイブリッド合成 → アセンブル
python emu.py                       # vendor/book/emu.py 経由で起動
```

起動後に：

- `ls` ── 利用可能なユーザープログラム一覧
- `exec hello.bin` ── サンプルプログラム実行
- `taskexec sleep.bin` ── 別タスクで非同期起動
- `Ctrl+]` に続けて `0`〜`3` ── 仮想コンソール切替
- `exit` ── OS 停止

### Simple C で 1 本コンパイル

```bash
python cc.py samples/hello.c        # → samples/hello.asm
python asm.py samples/hello.asm     # → samples/hello.bin
python test_run.py samples/hello.bin
```

`samples/` には 28 本のテストプログラムがあります。

## リポジトリ構成

```
Simple-C/
├── cc.py, cclex.py, ccparse.py, ccgen.py, ccpre.py   Simple C コンパイラ本体
├── cclib/runtime.asm                                  C 起動ランタイム
├── samples/*.c                                        Simple C テストプログラム
├── test_run.py                                        単発実行用ヘルパ
├── examples/
│   └── os/simple_os.c                                 Simple OS in C 本体
├── tools/
│   ├── setup.py                                       上流取得 + パッチ適用
│   ├── build_simple_os.py                             OS ビルドパイプライン
│   ├── build_simple_os_hybrid.py                      os.asm + simple_os.asm の合成
│   ├── check_simple_os_labels.py                      公開 ABI ラベル検査
│   ├── os_run.py                                      OS 動作 smoke runner
│   └── patches/emu_cr_fix.patch                       upstream emu.py 向けパッチ
├── Docs/
│   ├── Simple_C.md                                    Simple C 言語仕様と内部実装
│   ├── Simple_C.en.md                                 English summary
│   ├── Modifying_Simple_OS.md                         機能追加・削除ガイド
│   └── OriginalCPU.md                                 書籍由来の CPU 仕様参照
└── vendor/book/                                       setup.py が populate（gitignore 対象）
```

## ドキュメント

- [`Docs/Simple_C.md`](Docs/Simple_C.md) ── Simple C の言語サブセットと実装の解説
- [`Docs/Modifying_Simple_OS.md`](Docs/Modifying_Simple_OS.md) ── 機能追加・削除時の注意点
- [`Docs/OriginalCPU.md`](Docs/OriginalCPU.md) ── 書籍の独自 32 ビット CPU 仕様（参照用）

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照。

書籍由来のコード（`vendor/book/` 配下）は <https://github.com/sueyasu/os_book_code> のオリジナル MIT License に従います。本リポジトリには含まれません。
