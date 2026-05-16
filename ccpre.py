"""C プリプロセッサ（フェーズ7）

サポート:
  - #define NAME VALUE       オブジェクト形式マクロのみ
  - #include "file"          相対パス（ソースファイルのあるディレクトリ基準）
  - #include <file>          同上（システムパスは無し）

マクロ展開はソース文字列レベルで行うが、文字列リテラルと文字リテラルの
中身は触らない（簡易なスキャンで識別）。
"""
import os
import re


class PreprocessError(Exception):
    pass


_IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _expand_line(line, macros):
    """1行のソースにマクロ展開を施す。文字列/文字リテラルの中は飛ばす。"""
    out = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        # 文字列
        if c == '"':
            j = i
            i += 1
            while i < n and line[i] != '"':
                if line[i] == '\\' and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i = min(i + 1, n)
            out.append(line[j:i])
            continue
        # 文字
        if c == "'":
            j = i
            i += 1
            while i < n and line[i] != "'":
                if line[i] == '\\' and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i = min(i + 1, n)
            out.append(line[j:i])
            continue
        # 行コメント
        if c == '/' and i + 1 < n and line[i+1] == '/':
            out.append(line[i:])
            break
        # 識別子（ASCII のみ）
        m = _IDENT_RE.match(line, i)
        if m:
            word = m.group(0)
            i = m.end()
            if word in macros:
                out.append(macros[word])
            else:
                out.append(word)
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _process(src, base_dir, macros, included):
    """1ファイル分のプリプロセス。再帰的に #include を処理する。"""
    output = []
    for raw in src.splitlines():
        stripped = raw.strip()
        if stripped.startswith('#'):
            body = stripped[1:].lstrip()
            if body.startswith('define'):
                rest = body[6:].strip()
                if not rest:
                    raise PreprocessError("#define の書式が不正")
                m = _IDENT_RE.match(rest)
                if not m:
                    raise PreprocessError(f"#define の名前が不正: {rest}")
                name = m.group(0)
                value = rest[m.end():].strip()
                macros[name] = value
                output.append('')
                continue
            if body.startswith('include'):
                rest = body[7:].strip()
                if rest.startswith('"') and rest.endswith('"'):
                    inc_name = rest[1:-1]
                elif rest.startswith('<') and rest.endswith('>'):
                    inc_name = rest[1:-1]
                else:
                    raise PreprocessError(f"#include の書式が不正: {rest}")
                inc_path = os.path.join(base_dir, inc_name)
                inc_path = os.path.abspath(inc_path)
                if inc_path in included:
                    output.append('')
                    continue
                included.add(inc_path)
                if not os.path.exists(inc_path):
                    raise PreprocessError(f"#include のファイルが見つからない: {inc_path}")
                with open(inc_path, 'r', encoding='utf-8') as f:
                    inc_src = f.read()
                inc_out = _process(inc_src, os.path.dirname(inc_path), macros, included)
                output.append(inc_out)
                continue
            # その他の # ディレクティブは未対応（無視）
            output.append('')
            continue
        # マクロ展開
        output.append(_expand_line(raw, macros))
    return '\n'.join(output)


def preprocess(src, base_dir):
    """src 文字列にプリプロセスを施し、新しい文字列を返す。base_dir は #include の探索基準。"""
    macros = {}
    included = set()
    return _process(src, base_dir, macros, included)
