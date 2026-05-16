"""C字句解析器（フェーズ1〜5）

トークンは (kind, value, line) のタプル。
"""

KEYWORDS = {'return', 'int', 'char', 'if', 'else', 'while', 'for',
            'do', 'switch', 'case', 'default', 'break', 'continue',
            'goto', 'auto', 'static', 'extern', 'struct', 'asm', 'sizeof'}

# バックスラッシュエスケープ
ESCAPES = {
    'n': 0x0A, 't': 0x09, 'r': 0x0D, '0': 0x00,
    '\\': 0x5C, '"': 0x22, "'": 0x27, 'b': 0x08, 'a': 0x07,
    'f': 0x0C, 'v': 0x0B,
}


class LexError(Exception):
    pass


def _read_escape(src, i, n, line):
    """src[i] が '\\' の直後を指すとき、エスケープ文字を1バイトに変換して(値, 次の位置)を返す。"""
    if i >= n:
        raise LexError(f"Line {line}: 不完全なエスケープ")
    c = src[i]
    # \xNN
    if c == 'x':
        j = i + 1
        hex_start = j
        while j < n and j - hex_start < 2 and (src[j].isdigit() or src[j].lower() in 'abcdef'):
            j += 1
        if j == hex_start:
            raise LexError(f"Line {line}: \\x の後ろに16進数が必要")
        return int(src[hex_start:j], 16) & 0xFF, j
    if c in ESCAPES:
        return ESCAPES[c], i + 1
    # 未知のエスケープはそのまま
    return ord(c), i + 1


def tokenize(src):
    tokens = []
    i = 0
    line = 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if c == '/' and i + 1 < n and src[i+1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i+1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i+1] == '/'):
                if src[i] == '\n':
                    line += 1
                i += 1
            i += 2
            continue
        # 文字列リテラル
        if c == '"':
            i += 1
            buf = bytearray()
            while i < n and src[i] != '"':
                if src[i] == '\\':
                    val, i = _read_escape(src, i + 1, n, line)
                    buf.append(val)
                else:
                    if src[i] == '\n':
                        line += 1
                    buf.append(ord(src[i]) & 0xFF)
                    i += 1
            if i >= n:
                raise LexError(f"Line {line}: 文字列リテラルが閉じていません")
            i += 1  # 終端の "
            tokens.append(('STRLIT', bytes(buf), line))
            continue
        # 文字リテラル
        if c == "'":
            i += 1
            if i >= n:
                raise LexError(f"Line {line}: 文字リテラルが不完全")
            if src[i] == '\\':
                val, i = _read_escape(src, i + 1, n, line)
            else:
                val = ord(src[i]) & 0xFF
                i += 1
            if i >= n or src[i] != "'":
                raise LexError(f"Line {line}: 文字リテラルが閉じていません")
            i += 1
            tokens.append(('NUM', val, line))
            continue
        # 16進数リテラル
        if c == '0' and i + 1 < n and src[i+1] in ('x', 'X'):
            j = i + 2
            while j < n and (src[j].isdigit() or src[j].lower() in 'abcdef'):
                j += 1
            tokens.append(('NUM', int(src[i:j], 16), line))
            i = j
            continue
        # 10進数リテラル
        if c.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            tokens.append(('NUM', int(src[i:j]), line))
            i = j
            continue
        # 識別子・キーワード
        if c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            word = src[i:j]
            if word in KEYWORDS:
                tokens.append((word.upper(), word, line))
            else:
                tokens.append(('IDENT', word, line))
            i = j
            continue
        # 2文字記号
        two = src[i:i+2]
        two_map = {'++': 'PLUSPLUS', '--': 'MINUSMINUS',
                   '==': 'EQ', '!=': 'NE',
                   '<=': 'LE', '>=': 'GE',
                   '&&': 'LAND', '||': 'LOR',
                   '->': 'ARROW',
                   '<<': 'SHL', '>>': 'SHR'}
        if two in two_map:
            tokens.append((two_map[two], two, line))
            i += 2
            continue
        # 1文字記号
        single = {'+': 'PLUS', '-': 'MINUS', '*': 'STAR', '/': 'SLASH',
                  '%': 'PERCENT', '(': 'LPAREN', ')': 'RPAREN',
                  '{': 'LBRACE', '}': 'RBRACE', ';': 'SEMI', ',': 'COMMA',
                  '=': 'ASSIGN',
                  '<': 'LT', '>': 'GT', '!': 'NOT',
                  '&': 'AMP', '[': 'LBRACK', ']': 'RBRACK',
                  '.': 'DOT',
                  '|': 'BAR', '^': 'CARET', '~': 'TILDE'}
        if c in single:
            tokens.append((single[c], c, line))
            i += 1
            continue
        raise LexError(f"Line {line}: 未対応の文字: {c!r}")

    tokens.append(('EOF', None, line))
    return tokens
