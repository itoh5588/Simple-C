"""C構文解析器（フェーズ1〜7）

再帰下降パーサ。型情報は Type で表現する。
トップレベルは: struct定義 / 関数定義 / グローバル変数宣言 のいずれか。
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ── 型 ──────────────────────────────────────────────
@dataclass
class Type:
    kind: str                       # 'int', 'char', 'pointer', 'array', 'struct'
    base: Optional['Type'] = None   # pointer/array の指す先・要素型
    size: Optional[int] = None      # array の要素数
    name: Optional[str] = None      # struct のタグ名


INT_T = Type('int')
CHAR_T = Type('char')


def ptr(t):
    return Type('pointer', base=t)


# ── 式ノード ────────────────────────────────────────
@dataclass
class IntLit:
    value: int


@dataclass
class StringLit:
    data: bytes


@dataclass
class Sizeof:
    target: Any
    is_type: bool = False


@dataclass
class InitList:
    values: List[Any] = field(default_factory=list)


@dataclass
class Var:
    name: str


@dataclass
class UnaryOp:
    op: str
    operand: Any


@dataclass
class AddrOf:
    operand: Any


@dataclass
class Deref:
    operand: Any


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass
class Assign:
    target: Any
    value: Any


@dataclass
class IncDec:
    op: str
    operand: Any
    is_prefix: bool


@dataclass
class Call:
    name: str
    args: List[Any] = field(default_factory=list)


@dataclass
class Member:
    """obj.name の形（-> はパース時に obj→Deref(obj) に書き換え）"""
    object: Any
    name: str


# ── 文ノード ────────────────────────────────────────
@dataclass
class VarDecl:
    type: Type
    name: str
    init: Optional[Any] = None


@dataclass
class ExprStmt:
    expr: Any


@dataclass
class Return:
    expr: Any


@dataclass
class If:
    cond: Any
    then: Any
    else_: Optional[Any]


@dataclass
class While:
    cond: Any
    body: Any


@dataclass
class For:
    init: Optional[Any]
    cond: Optional[Any]
    update: Optional[Any]
    body: Any


@dataclass
class Break:
    pass


@dataclass
class Continue:
    pass


@dataclass
class Block:
    stmts: List[Any] = field(default_factory=list)


@dataclass
class InlineAsm:
    code: str


@dataclass
class Param:
    name: str
    type: Type


@dataclass
class Function:
    name: str
    params: List[Param] = field(default_factory=list)
    body: List[Any] = field(default_factory=list)
    return_type: Type = field(default_factory=lambda: INT_T)


@dataclass
class StructDef:
    name: str
    members: List[Param] = field(default_factory=list)


@dataclass
class Program:
    functions: List[Function] = field(default_factory=list)
    globals: List[VarDecl] = field(default_factory=list)
    structs: List[StructDef] = field(default_factory=list)
    items: List[Any] = field(default_factory=list)


class ParseError(Exception):
    pass


TYPE_KEYWORDS = ('INT', 'CHAR', 'STRUCT')


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0

    def peek(self, offset=0):
        return self.toks[self.pos + offset]

    def advance(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def expect(self, kind):
        t = self.advance()
        if t[0] != kind:
            raise ParseError(
                f"Line {t[2]}: {kind} を期待しましたが {t[0]} ({t[1]!r}) でした")
        return t

    # ── トップレベル ──────────────────────────────────
    def parse_program(self):
        funcs = []
        globals_ = []
        structs = []
        items = []
        while self.peek()[0] != 'EOF':
            if self.peek()[0] == 'ASM':
                item = self.parse_inline_asm()
                items.append(item)
                continue
            # struct 定義: 'struct' IDENT '{'
            if (self.peek()[0] == 'STRUCT'
                    and self.peek(1)[0] == 'IDENT'
                    and self.peek(2)[0] == 'LBRACE'):
                sd = self._parse_struct_def()
                structs.append(sd)
                continue
            # 関数定義 または グローバル変数宣言
            base_type = self._parse_base_type()
            name, full_type = self._parse_declarator_rest(base_type)
            if self.peek()[0] == 'LPAREN':
                fn = self._parse_function_rest(name, full_type)
                funcs.append(fn)
                items.append(fn)
            else:
                decls = self._parse_global_vars_rest(name, full_type, base_type)
                globals_.extend(decls)
        return Program(funcs, globals_, structs, items)

    def _parse_struct_def(self):
        self.expect('STRUCT')
        name = self.expect('IDENT')[1]
        self.expect('LBRACE')
        members = []
        while self.peek()[0] != 'RBRACE':
            base = self._parse_base_type()
            while True:
                mname, mtype = self._parse_declarator_rest(base)
                members.append(Param(mname, mtype))
                if self.peek()[0] == 'COMMA':
                    self.advance()
                    continue
                break
            self.expect('SEMI')
        self.expect('RBRACE')
        self.expect('SEMI')
        return StructDef(name, members)

    def _parse_base_type(self):
        t = self.peek()
        if t[0] == 'INT':
            self.advance()
            return INT_T
        if t[0] == 'CHAR':
            self.advance()
            return CHAR_T
        if t[0] == 'STRUCT':
            self.advance()
            tag = self.expect('IDENT')[1]
            return Type('struct', name=tag)
        raise ParseError(f"Line {t[2]}: 型を期待しましたが {t[1]!r} でした")

    def _parse_declarator_rest(self, base_type):
        """'*'* IDENT ('[' NUM? ']')? を解析。(name, full_type) を返す。"""
        t = base_type
        while self.peek()[0] == 'STAR':
            self.advance()
            t = ptr(t)
        name = self.expect('IDENT')[1]
        if self.peek()[0] == 'LBRACK':
            self.advance()
            size = None
            if self.peek()[0] != 'RBRACK':
                size = self.expect('NUM')[1]
            self.expect('RBRACK')
            t = Type('array', base=t, size=size)
        return name, t

    def _parse_function_rest(self, name, return_type):
        """name と return_type は既に消費済み。'(' から先を解析する。"""
        self.expect('LPAREN')
        params = []
        if self.peek()[0] != 'RPAREN':
            if self.peek()[0] in TYPE_KEYWORDS:
                while True:
                    base = self._parse_base_type()
                    pname, ptype = self._parse_declarator_rest(base)
                    params.append(Param(pname, ptype))
                    if self.peek()[0] == 'COMMA':
                        self.advance()
                        continue
                    break
            else:
                # K&R 形式: 名前のみ
                while True:
                    pname = self.expect('IDENT')[1]
                    params.append(Param(pname, INT_T))
                    if self.peek()[0] == 'COMMA':
                        self.advance()
                        continue
                    break
        self.expect('RPAREN')

        # K&R: ここに型宣言が並ぶ
        while self.peek()[0] in TYPE_KEYWORDS:
            base = self._parse_base_type()
            while True:
                pname, ptype = self._parse_declarator_rest(base)
                matched = False
                for p in params:
                    if p.name == pname:
                        p.type = ptype
                        matched = True
                        break
                if not matched:
                    raise ParseError(
                        f"宣言された引数 {pname} が引数リストにない")
                if self.peek()[0] == 'COMMA':
                    self.advance()
                    continue
                break
            self.expect('SEMI')

        self.expect('LBRACE')
        body = []
        while self.peek()[0] != 'RBRACE':
            body.append(self.parse_stmt())
        self.expect('RBRACE')
        return Function(name, params, body, return_type)

    def _parse_global_vars_rest(self, first_name, first_type, base_type):
        """最初の名前と型は既に消費済み。続きとセミコロンまでを解析。"""
        decls = []
        init = None
        if self.peek()[0] == 'ASSIGN':
            self.advance()
            init = self.parse_initializer()
        decls.append(VarDecl(first_type, first_name, init))
        while self.peek()[0] == 'COMMA':
            self.advance()
            name, ft = self._parse_declarator_rest(base_type)
            init = None
            if self.peek()[0] == 'ASSIGN':
                self.advance()
                init = self.parse_initializer()
            decls.append(VarDecl(ft, name, init))
        self.expect('SEMI')
        return decls

    # ── 文 ────────────────────────────────────────────
    def parse_stmt(self):
        t = self.peek()
        if t[0] in TYPE_KEYWORDS:
            return self.parse_decl()
        if t[0] == 'RETURN':
            self.advance()
            e = self.parse_expr()
            self.expect('SEMI')
            return Return(e)
        if t[0] == 'IF':
            return self.parse_if()
        if t[0] == 'WHILE':
            return self.parse_while()
        if t[0] == 'FOR':
            return self.parse_for()
        if t[0] == 'BREAK':
            self.advance()
            self.expect('SEMI')
            return Break()
        if t[0] == 'CONTINUE':
            self.advance()
            self.expect('SEMI')
            return Continue()
        if t[0] == 'LBRACE':
            return self.parse_block()
        if t[0] == 'ASM':
            return self.parse_inline_asm()
        if t[0] == 'SEMI':
            self.advance()
            return ExprStmt(IntLit(0))
        e = self.parse_expr()
        self.expect('SEMI')
        return ExprStmt(e)

    def parse_block(self):
        self.expect('LBRACE')
        stmts = []
        while self.peek()[0] != 'RBRACE':
            stmts.append(self.parse_stmt())
        self.expect('RBRACE')
        return Block(stmts)

    def parse_inline_asm(self):
        self.expect('ASM')
        self.expect('LPAREN')
        tok = self.expect('STRLIT')
        self.expect('RPAREN')
        self.expect('SEMI')
        code = tok[1].decode('utf-8', errors='replace')
        return InlineAsm(code)

    def parse_if(self):
        self.expect('IF')
        self.expect('LPAREN')
        cond = self.parse_expr()
        self.expect('RPAREN')
        then = self.parse_stmt()
        else_ = None
        if self.peek()[0] == 'ELSE':
            self.advance()
            else_ = self.parse_stmt()
        return If(cond, then, else_)

    def parse_while(self):
        self.expect('WHILE')
        self.expect('LPAREN')
        cond = self.parse_expr()
        self.expect('RPAREN')
        body = self.parse_stmt()
        return While(cond, body)

    def parse_for(self):
        self.expect('FOR')
        self.expect('LPAREN')
        init = None
        if self.peek()[0] != 'SEMI':
            init = self.parse_expr()
        self.expect('SEMI')
        cond = None
        if self.peek()[0] != 'SEMI':
            cond = self.parse_expr()
        self.expect('SEMI')
        update = None
        if self.peek()[0] != 'RPAREN':
            update = self.parse_expr()
        self.expect('RPAREN')
        body = self.parse_stmt()
        return For(init, cond, update, body)

    def parse_decl(self):
        base = self._parse_base_type()
        decls = []
        while True:
            name, full_type = self._parse_declarator_rest(base)
            init = None
            if self.peek()[0] == 'ASSIGN':
                self.advance()
                init = self.parse_initializer()
            decls.append(VarDecl(full_type, name, init))
            if self.peek()[0] == 'COMMA':
                self.advance()
                continue
            break
        self.expect('SEMI')
        if len(decls) == 1:
            return decls[0]
        return decls

    def parse_initializer(self):
        if self.peek()[0] != 'LBRACE':
            return self.parse_assign_expr()
        self.advance()
        values = []
        if self.peek()[0] != 'RBRACE':
            values.append(self.parse_assign_expr())
            while self.peek()[0] == 'COMMA':
                self.advance()
                if self.peek()[0] == 'RBRACE':
                    break
                values.append(self.parse_assign_expr())
        self.expect('RBRACE')
        return InitList(values)

    # ── 式 ────────────────────────────────────────────
    def parse_expr(self):
        return self.parse_assign_expr()

    def parse_assign_expr(self):
        left = self.parse_lor()
        if self.peek()[0] == 'ASSIGN':
            self.advance()
            right = self.parse_assign_expr()
            return Assign(left, right)
        return left

    def parse_lor(self):
        left = self.parse_land()
        while self.peek()[0] == 'LOR':
            self.advance()
            right = self.parse_land()
            left = BinOp('||', left, right)
        return left

    def parse_land(self):
        left = self.parse_bitor()
        while self.peek()[0] == 'LAND':
            self.advance()
            right = self.parse_bitor()
            left = BinOp('&&', left, right)
        return left

    def parse_bitor(self):
        left = self.parse_bitxor()
        while self.peek()[0] == 'BAR':
            self.advance()
            right = self.parse_bitxor()
            left = BinOp('|', left, right)
        return left

    def parse_bitxor(self):
        left = self.parse_bitand()
        while self.peek()[0] == 'CARET':
            self.advance()
            right = self.parse_bitand()
            left = BinOp('^', left, right)
        return left

    def parse_bitand(self):
        left = self.parse_equality()
        while self.peek()[0] == 'AMP':
            self.advance()
            right = self.parse_equality()
            left = BinOp('&', left, right)
        return left

    def parse_equality(self):
        left = self.parse_relational()
        while self.peek()[0] in ('EQ', 'NE'):
            op = self.advance()[1]
            right = self.parse_relational()
            left = BinOp(op, left, right)
        return left

    def parse_relational(self):
        left = self.parse_shift()
        while self.peek()[0] in ('LT', 'LE', 'GT', 'GE'):
            op = self.advance()[1]
            right = self.parse_shift()
            left = BinOp(op, left, right)
        return left

    def parse_shift(self):
        left = self.parse_additive()
        while self.peek()[0] in ('SHL', 'SHR'):
            op = self.advance()[1]
            right = self.parse_additive()
            left = BinOp(op, left, right)
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek()[0] in ('PLUS', 'MINUS'):
            op = self.advance()[1]
            right = self.parse_multiplicative()
            left = BinOp(op, left, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.peek()[0] in ('STAR', 'SLASH', 'PERCENT'):
            op = self.advance()[1]
            right = self.parse_unary()
            left = BinOp(op, left, right)
        return left

    def parse_unary(self):
        t = self.peek()
        if t[0] == 'MINUS':
            self.advance()
            return UnaryOp('-', self.parse_unary())
        if t[0] == 'PLUS':
            self.advance()
            return self.parse_unary()
        if t[0] == 'NOT':
            self.advance()
            return UnaryOp('!', self.parse_unary())
        if t[0] == 'TILDE':
            self.advance()
            return UnaryOp('~', self.parse_unary())
        if t[0] == 'SIZEOF':
            self.advance()
            if self.peek()[0] == 'LPAREN' and self.peek(1)[0] in TYPE_KEYWORDS:
                self.advance()
                base = self._parse_base_type()
                _, full_type = self._parse_abstract_declarator(base)
                self.expect('RPAREN')
                return Sizeof(full_type, is_type=True)
            return Sizeof(self.parse_unary(), is_type=False)
        if t[0] == 'AMP':
            self.advance()
            return AddrOf(self.parse_unary())
        if t[0] == 'STAR':
            self.advance()
            return Deref(self.parse_unary())
        if t[0] == 'PLUSPLUS':
            self.advance()
            return IncDec('++', self.parse_unary(), is_prefix=True)
        if t[0] == 'MINUSMINUS':
            self.advance()
            return IncDec('--', self.parse_unary(), is_prefix=True)
        return self.parse_postfix()

    def _parse_abstract_declarator(self, base_type):
        """sizeof 用に '*'+ と '[NUM]' だけを読む。名前は不要。"""
        t = base_type
        while self.peek()[0] == 'STAR':
            self.advance()
            t = ptr(t)
        if self.peek()[0] == 'LBRACK':
            self.advance()
            size = self.expect('NUM')[1]
            self.expect('RBRACK')
            t = Type('array', base=t, size=size)
        return None, t

    def parse_postfix(self):
        e = self.parse_primary()
        while True:
            t = self.peek()
            if t[0] == 'PLUSPLUS':
                self.advance()
                e = IncDec('++', e, is_prefix=False)
                continue
            if t[0] == 'MINUSMINUS':
                self.advance()
                e = IncDec('--', e, is_prefix=False)
                continue
            if t[0] == 'LBRACK':
                self.advance()
                idx = self.parse_expr()
                self.expect('RBRACK')
                e = Deref(BinOp('+', e, idx))
                continue
            if t[0] == 'DOT':
                self.advance()
                mname = self.expect('IDENT')[1]
                e = Member(e, mname)
                continue
            if t[0] == 'ARROW':
                self.advance()
                mname = self.expect('IDENT')[1]
                # p->m を (*p).m に書き換え
                e = Member(Deref(e), mname)
                continue
            if t[0] == 'LPAREN':
                if not isinstance(e, Var):
                    raise ParseError(
                        f"Line {t[2]}: 関数呼び出しの対象は識別子のみ")
                self.advance()
                args = []
                if self.peek()[0] != 'RPAREN':
                    args.append(self.parse_assign_expr())
                    while self.peek()[0] == 'COMMA':
                        self.advance()
                        args.append(self.parse_assign_expr())
                self.expect('RPAREN')
                e = Call(e.name, args)
                continue
            break
        return e

    def parse_primary(self):
        t = self.peek()
        if t[0] == 'NUM':
            self.advance()
            return IntLit(t[1])
        if t[0] == 'STRLIT':
            self.advance()
            return StringLit(t[1])
        if t[0] == 'IDENT':
            self.advance()
            return Var(t[1])
        if t[0] == 'LPAREN':
            self.advance()
            e = self.parse_expr()
            self.expect('RPAREN')
            return e
        raise ParseError(f"Line {t[2]}: 式を期待しましたが {t[1]!r} でした")


def parse(tokens):
    return Parser(tokens).parse_program()
