"""V6相当 Cコンパイラ駆動部

使い方: python cc.py [--no-runtime] <file.c>
  → <file.asm> を生成する。続けて python asm.py <file.asm> でバイナリ化。
  デフォルトで cclib/runtime.asm を末尾に取り込む。
"""
import os
import sys

from cclex import tokenize, LexError
from ccparse import parse, ParseError
from ccgen import generate, GenError
from ccpre import preprocess, PreprocessError


HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME_PATH = os.path.join(HERE, 'cclib', 'runtime.asm')


def compile_file(src_path, include_runtime=True):
    if not src_path.endswith('.c'):
        print("ファイルの拡張子が .c ではありません", file=sys.stderr)
        sys.exit(1)
    asm_path = src_path[:-2] + '.asm'

    with open(src_path, 'r', encoding='utf-8') as f:
        src = f.read()

    try:
        src = preprocess(src, os.path.dirname(os.path.abspath(src_path)))
        tokens = tokenize(src)
        ast = parse(tokens)
        asm = generate(ast)
    except (LexError, ParseError, GenError, PreprocessError) as e:
        print(f"[{src_path}] {e}", file=sys.stderr)
        sys.exit(1)

    if include_runtime and os.path.exists(RUNTIME_PATH):
        with open(RUNTIME_PATH, 'r', encoding='utf-8') as f:
            asm = asm + '\n' + f.read()

    with open(asm_path, 'w', encoding='utf-8') as f:
        f.write(asm)
    print(f"Wrote {asm_path}")


def main():
    args = sys.argv[1:]
    include_runtime = True
    sources = []
    for a in args:
        if a == '--no-runtime':
            include_runtime = False
        else:
            sources.append(a)
    if not sources:
        print("ソースファイル (.c) を指定してください", file=sys.stderr)
        sys.exit(1)
    for s in sources:
        compile_file(s, include_runtime=include_runtime)


if __name__ == '__main__':
    main()
