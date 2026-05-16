"""コード生成（フェーズ1〜7）

スタックベース評価。式の結果は常に R0 に置く。
型情報を使って char/int/pointer/array/struct を区別する。

ABI:
  - 引数は右から左にスタック push、戻り値は R0
  - caller-saved: R0〜R3, R8, R9   callee-saved: R4〜R7
  - R7 をフレームポインタ

ストレージ:
  - スカラ（int / char / pointer）: スタックでは 4バイトスロット、グローバルでは型に応じたサイズ
  - 配列: バイト単位（char）または 4 バイト単位（int 等）
  - struct: メンバを packed 配置（パディング無し）。フレームは 4の倍数に揃える

グローバル変数:
  - すべてのコードの後ろに `_g_<name>` ラベル付きで配置
  - 初期化子はコンパイル時定数（IntLit）のみ。それ以外は 0 で初期化

文字列リテラル:
  - 関数コードの後ろにラベル付きで .BYTE 列として出力
  - 値として使うと char* （文字列先頭アドレス）になる
"""
from ccparse import (
    IntLit, StringLit, Sizeof, InitList, Var, UnaryOp, AddrOf, Deref, BinOp,
    Assign, IncDec, VarDecl, ExprStmt, Return, If, While, For,
    Break, Continue, Block, InlineAsm, Call, Member,
    Function, StructDef, Program,
    Type, INT_T, CHAR_T, ptr,
)


class GenError(Exception):
    pass


BINOP_TO_INST = {
    '+': 'ADD',
    '-': 'SUB',
    '*': 'MUL',
    '/': 'DIV',
    '%': 'MOD',
    '&': 'AND',
    '|': 'OR',
    '^': 'XOR',
}

BINOP_TO_IMM_INST = {
    '+': 'ADDI',
    '-': 'SUBI',
    '*': 'MULI',
    '/': 'DIVI',
    '%': 'MODI',
    '&': 'ANDI',
    '|': 'ORI',
    '^': 'XORI',
}

IMM20_MAX = 0xFFFFF

CMP_OPS = ('==', '!=', '<', '<=', '>', '>=')


def _is_ptr_like(t):
    return t.kind in ('pointer', 'array')


class CodeGen:
    def __init__(self):
        self.lines = []
        # ローカル: name -> 符号付きバイトオフセット (R7 から)
        self.local_offsets = {}
        # ローカル: name -> Type
        self.local_types = {}
        # グローバル: name -> (label, Type, init_value or None)
        self.globals = {}
        self.global_order = []   # 宣言順
        # struct 定義: name -> StructDef
        self.structs = {}
        self.current_func = None
        self.label_counter = 0
        self.loop_stack = []
        self.string_pool = []
        # inline-asm builtin: ゼロ引数で本体が単一 InlineAsm の関数。
        # name -> InlineAsm code 文字列。呼び出し側で直接展開し、
        # 関数本体の emission はスキップする。
        self.inline_asm_builtins = {}

    # ── 出力ヘルパ ────────────────────────────────────
    def emit(self, line=''):
        self.lines.append(line)

    def emiti(self, instr):
        self.lines.append('        ' + instr)

    def output(self):
        self._run_peephole()
        return '\n'.join(self.lines) + '\n'

    def _run_peephole(self):
        """生成済み命令列に対する単純な peephole 最適化。

        意味的に同等で、かつフラグ更新の差が無い変換のみ:
        - JPI Lxxx の直後に Lxxx: ラベルがあれば JPI を削除
        - PUSH Rx の直後に POP Rx (同レジスタ) があれば両方削除
        - MOV Rx, Rx の自己 MOV を削除 (MOV はフラグを更新しない)
        """
        self._peephole_jpi_to_next_label()
        self._peephole_push_pop_adjacent()
        self._peephole_self_mov()

    def _peephole_jpi_to_next_label(self):
        out = []
        i = 0
        n = len(self.lines)
        while i < n:
            line = self.lines[i]
            parts = line.strip().split()
            if (len(parts) == 2 and parts[0] == 'JPI'
                    and i + 1 < n
                    and self.lines[i + 1].strip() == parts[1] + ':'):
                i += 1   # JPI を捨ててラベル行に進む
                continue
            out.append(line)
            i += 1
        self.lines = out

    def _peephole_push_pop_adjacent(self):
        out = []
        i = 0
        n = len(self.lines)
        while i < n:
            line = self.lines[i]
            parts = line.strip().split()
            if (len(parts) == 2 and parts[0] == 'PUSH'
                    and i + 1 < n):
                np = self.lines[i + 1].strip().split()
                if len(np) == 2 and np[0] == 'POP' and np[1] == parts[1]:
                    i += 2
                    continue
            out.append(line)
            i += 1
        self.lines = out

    def _peephole_self_mov(self):
        out = []
        for line in self.lines:
            parts = line.strip().replace(',', '').split()
            if (len(parts) == 3 and parts[0] == 'MOV'
                    and parts[1] == parts[2]):
                continue
            out.append(line)
        self.lines = out

    def _new_label(self, prefix='L'):
        self.label_counter += 1
        return f"_{prefix}_{self.label_counter}"

    # ── サイズ計算 ────────────────────────────────────
    def _elem_size(self, t):
        base = t.base
        if base is None:
            return 4
        if base.kind == 'char':
            return 1
        if base.kind == 'struct':
            return self._struct_size(base.name)
        return 4

    def _member_size(self, t):
        """struct メンバの packed サイズ。"""
        if t.kind == 'char':
            return 1
        if t.kind in ('int', 'pointer'):
            return 4
        if t.kind == 'array':
            if t.size is None:
                raise GenError("サイズ未確定の配列")
            elem = self._sizeof_type(t.base)
            return t.size * elem
        if t.kind == 'struct':
            return self._struct_size(t.name)
        return 4

    def _struct_size(self, name):
        sd = self.structs.get(name)
        if sd is None:
            raise GenError(f"未定義の struct: {name}")
        size = 0
        for m in sd.members:
            size += self._member_size(m.type)
        return size

    def _var_size(self, t):
        """ローカル／グローバルの占有バイト数。4 の倍数に丸める。"""
        if t.kind in ('int', 'pointer', 'char'):
            return 4
        if t.kind == 'array':
            if t.size is None:
                raise GenError("サイズ未確定の配列")
            elem = self._sizeof_type(t.base)
            total = t.size * elem
            return (total + 3) & ~3
        if t.kind == 'struct':
            return (self._struct_size(t.name) + 3) & ~3
        return 4

    def _find_member(self, struct_name, member_name):
        sd = self.structs.get(struct_name)
        if sd is None:
            raise GenError(f"未定義の struct: {struct_name}")
        offset = 0
        for m in sd.members:
            if m.name == member_name:
                return offset, m.type
            offset += self._member_size(m.type)
        raise GenError(f"struct {struct_name} にメンバ {member_name} は無い")

    # ── 型推論 ────────────────────────────────────────
    def type_of(self, e):
        if isinstance(e, IntLit):
            return INT_T
        if isinstance(e, StringLit):
            return ptr(CHAR_T)
        if isinstance(e, Sizeof):
            return INT_T
        if isinstance(e, Var):
            t = self._lookup_type(e.name)
            if t.kind == 'array':
                return ptr(t.base)
            return t
        if isinstance(e, AddrOf):
            if isinstance(e.operand, Var):
                base = self._lookup_type(e.operand.name)
                return ptr(base)
            if isinstance(e.operand, Deref):
                return self.type_of(e.operand.operand)
            if isinstance(e.operand, Member):
                _, mtype = self._member_info(e.operand)
                return ptr(mtype)
            return ptr(INT_T)
        if isinstance(e, Deref):
            t = self.type_of(e.operand)
            if _is_ptr_like(t):
                return t.base
            return INT_T
        if isinstance(e, BinOp):
            if e.op in ('+', '-'):
                lt = self.type_of(e.left)
                rt = self.type_of(e.right)
                if _is_ptr_like(lt):
                    return lt if lt.kind == 'pointer' else ptr(lt.base)
                if _is_ptr_like(rt) and e.op == '+':
                    return rt if rt.kind == 'pointer' else ptr(rt.base)
            return INT_T
        if isinstance(e, UnaryOp):
            return self.type_of(e.operand)
        if isinstance(e, Assign):
            return self.type_of(e.target)
        if isinstance(e, IncDec):
            return self.type_of(e.operand)
        if isinstance(e, Call):
            return INT_T
        if isinstance(e, Member):
            _, mtype = self._member_info(e)
            if mtype.kind == 'array':
                return ptr(mtype.base)
            return mtype
        return INT_T

    def _member_info(self, member):
        """Member ノードを受け取り、(offset, type) を返す。"""
        obj_t = self._struct_type_of(member.object)
        return self._find_member(obj_t.name, member.name)

    def _struct_type_of(self, e):
        """e は struct 型の lvalue 相当のはず。その struct 型を返す。"""
        if isinstance(e, Var):
            t = self._lookup_type(e.name)
            if t.kind != 'struct':
                raise GenError(f"struct でない: {e.name}")
            return t
        if isinstance(e, Deref):
            t = self.type_of(e.operand)
            if t.kind != 'pointer' or t.base.kind != 'struct':
                raise GenError(f"struct* でない")
            return t.base
        if isinstance(e, Member):
            _, mtype = self._member_info(e)
            if mtype.kind != 'struct':
                raise GenError(f"struct でない member")
            return mtype
        raise GenError(f"struct アクセスの対象が不正: {e!r}")

    def _lookup_type(self, name):
        if name in self.local_types:
            return self.local_types[name]
        if name in self.globals:
            return self.globals[name][1]
        raise GenError(f"未定義の変数: {name}")

    def _sizeof_type(self, t):
        if t.kind == 'char':
            return 1
        if t.kind in ('int', 'pointer'):
            return 4
        if t.kind == 'array':
            if t.size is None:
                raise GenError("サイズ未確定の配列に sizeof は使えません")
            return t.size * self._sizeof_type(t.base)
        if t.kind == 'struct':
            return self._struct_size(t.name)
        return 4

    def _sizeof_expr(self, e):
        if isinstance(e, Var):
            return self._sizeof_type(self._lookup_type(e.name))
        if isinstance(e, Member):
            _, mtype = self._member_info(e)
            return self._sizeof_type(mtype)
        return self._sizeof_type(self.type_of(e))

    def _infer_array_size(self, t, init):
        if t.kind != 'array' or t.size is not None:
            return
        if isinstance(init, StringLit) and t.base.kind == 'char':
            t.size = len(init.data) + 1
            return
        if isinstance(init, InitList):
            t.size = len(init.values)
            return
        raise GenError("サイズ省略の配列には初期化子が必要")

    # ── 駆動 ──────────────────────────────────────────
    def gen_program(self, prog):
        # struct を登録
        for sd in prog.structs:
            if sd.name in self.structs:
                raise GenError(f"struct {sd.name} の二重定義")
            self.structs[sd.name] = sd

        # グローバルを登録
        for d in prog.globals:
            self._infer_array_size(d.type, d.init)
            if d.name in self.globals:
                raise GenError(f"グローバル {d.name} の二重定義")
            label = f"_g_{d.name}"
            self.globals[d.name] = (label, d.type, d.init)
            self.global_order.append(d.name)

        # ゼロ引数 + 本体が単一 InlineAsm の関数を builtin として登録
        for f in prog.functions:
            code = self._extract_inline_asm_builtin(f)
            if code is not None:
                self.inline_asm_builtins[f.name] = code

        main_func = None
        others = []
        for f in prog.functions:
            if f.name == 'main':
                main_func = f
            else:
                others.append(f)
        if main_func is None:
            raise GenError("main 関数が見つかりません")

        self.emit("; Generated by cc.py")
        if any(isinstance(item, InlineAsm) for item in prog.items):
            for item in prog.items:
                if isinstance(item, InlineAsm):
                    self._emit_inline_asm(item)
                elif isinstance(item, Function):
                    if item.name in self.inline_asm_builtins:
                        continue
                    self.gen_function(item)
        else:
            self.gen_function(main_func)
            for f in others:
                if f.name in self.inline_asm_builtins:
                    continue
                self.gen_function(f)
        self._emit_string_pool()
        self._emit_globals()

    def gen_function(self, func):
        # body の平坦化
        stmts = []
        for s in func.body:
            if isinstance(s, list):
                stmts.extend(s)
            else:
                stmts.append(s)

        # 引数を登録（正のオフセット、4 バイトずつ）
        self.local_offsets = {}
        self.local_types = {}
        for k, p in enumerate(func.params):
            if p.name in self.local_offsets:
                raise GenError(f"引数 {p.name} の二重宣言")
            self.local_offsets[p.name] = 8 + 4 * k
            self.local_types[p.name] = p.type

        # ローカル変数（負のオフセット、宣言順、可変サイズ）
        local_decls = []
        for s in stmts:
            self._collect_locals(s, local_decls)
        cum = 0
        for d in local_decls:
            self._infer_array_size(d.type, d.init)
            size = self._var_size(d.type)
            cum += size
            if d.name in self.local_offsets:
                raise GenError(f"変数 {d.name} は引数と衝突")
            self.local_offsets[d.name] = -cum
            self.local_types[d.name] = d.type
        frame_size = cum

        self.current_func = func.name
        self.emit(f"{func.name}:")
        self.emiti("PUSH    R7")
        self.emiti("MOV     R7, SP")
        if frame_size > 0:
            self.emiti(f"SUBI    SP, {frame_size}")

        for s in stmts:
            self.gen_stmt(s)

        self.emit(f"_{func.name}_done:")
        self.emiti("MOV     SP, R7")
        self.emiti("POP     R7")
        self.emiti("RET")

    def _collect_locals(self, node, out):
        if isinstance(node, list):
            for n in node:
                self._collect_locals(n, out)
            return
        if isinstance(node, VarDecl):
            for d in out:
                if d.name == node.name:
                    raise GenError(f"変数 {node.name} の二重宣言")
            out.append(node)
            return
        if isinstance(node, Block):
            for s in node.stmts:
                self._collect_locals(s, out)
            return
        if isinstance(node, If):
            self._collect_locals(node.then, out)
            if node.else_ is not None:
                self._collect_locals(node.else_, out)
            return
        if isinstance(node, While):
            self._collect_locals(node.body, out)
            return
        if isinstance(node, For):
            self._collect_locals(node.body, out)
            return

    def _emit_string_pool(self):
        if not self.string_pool:
            return
        self.emit("; ── string pool ──")
        for label, data in self.string_pool:
            self.emit(f"{label}:")
            for b in data:
                self.emiti(f".BYTE   {b}")
            self.emiti(".BYTE   0")

    def _emit_globals(self):
        if not self.globals:
            return
        self.emit("; ── globals ──")
        for name in self.global_order:
            label, t, init = self.globals[name]
            self.emit(f"{label}:")
            self._emit_global_init(t, init)

    def _emit_global_init(self, t, init):
        if t.kind == 'char':
            v = self._eval_const(init) if init is not None else 0
            self.emiti(f".BYTE   {v & 0xFF}")
            return
        if t.kind in ('int', 'pointer'):
            v = self._eval_const(init) if init is not None else 0
            self.emiti(f".DWORD  {v & 0xFFFFFFFF}")
            return
        if t.kind == 'array':
            data = self._global_array_bytes(t, init)
            for b in data:
                self.emiti(f".BYTE   {b}")
            return
        if t.kind == 'struct':
            if init is not None:
                raise GenError("struct の初期化子は未対応")
            n_bytes = self._var_size(t)
            for _ in range(n_bytes):
                self.emiti(".BYTE   0")
            return
        raise GenError(f"未対応のグローバル型: {t}")

    def _global_array_bytes(self, t, init):
        if t.size is None:
            raise GenError("サイズ未確定の配列")

        raw = bytearray()
        if init is None:
            pass
        elif isinstance(init, StringLit) and t.base.kind == 'char':
            raw.extend(init.data)
            raw.append(0)
        elif isinstance(init, InitList):
            for vexpr in init.values:
                v = self._eval_const(vexpr)
                if t.base.kind == 'char':
                    raw.append(v & 0xFF)
                else:
                    v &= 0xFFFFFFFF
                    raw.extend(((v >> 24) & 0xFF, (v >> 16) & 0xFF,
                                (v >> 8) & 0xFF, v & 0xFF))
        else:
            raise GenError("配列の初期化子は文字列または {...} のみ")

        logical_size = t.size * self._sizeof_type(t.base)
        if len(raw) > logical_size:
            raise GenError("配列初期化子が要素数を超えています")
        total = self._var_size(t)
        while len(raw) < total:
            raw.append(0)
        return raw

    def _eval_const(self, e):
        """コンパイル時定数を評価。IntLit のみ許容。"""
        if isinstance(e, IntLit):
            return e.value
        if isinstance(e, Sizeof):
            return self._sizeof_type(e.target) if e.is_type else self._sizeof_expr(e.target)
        if isinstance(e, UnaryOp) and e.op == '-':
            v = self._eval_const(e.operand)
            return (-v) & 0xFFFFFFFF
        if isinstance(e, UnaryOp) and e.op == '~':
            v = self._eval_const(e.operand)
            return (~v) & 0xFFFFFFFF
        if isinstance(e, BinOp):
            l = self._eval_const(e.left)
            r = self._eval_const(e.right)
            if e.op == '+':
                return (l + r) & 0xFFFFFFFF
            if e.op == '-':
                return (l - r) & 0xFFFFFFFF
            if e.op == '*':
                return (l * r) & 0xFFFFFFFF
            if e.op == '/':
                return (l // r) & 0xFFFFFFFF
            if e.op == '%':
                return (l % r) & 0xFFFFFFFF
            if e.op == '&':
                return (l & r) & 0xFFFFFFFF
            if e.op == '|':
                return (l | r) & 0xFFFFFFFF
            if e.op == '^':
                return (l ^ r) & 0xFFFFFFFF
            if e.op == '<<':
                return (l << r) & 0xFFFFFFFF
            if e.op == '>>':
                return (l >> r) & 0xFFFFFFFF
        raise GenError("グローバル初期化子はコンパイル時定数のみ")

    # ── 文 ────────────────────────────────────────────
    def gen_stmt(self, stmt):
        if isinstance(stmt, Return):
            self.gen_expr(stmt.expr)
            self.emiti(f"JPI     _{self.current_func}_done")
            return
        if isinstance(stmt, VarDecl):
            if stmt.init is not None:
                t = self.local_types[stmt.name]
                if t.kind == 'array':
                    raise GenError(f"配列 {stmt.name} の初期化は未対応")
                if t.kind == 'struct':
                    raise GenError(f"struct {stmt.name} の初期化は未対応")
                self.gen_expr(stmt.init)
                self._store_to_var(stmt.name)
            return
        if isinstance(stmt, ExprStmt):
            self.gen_expr(stmt.expr)
            return
        if isinstance(stmt, Block):
            for s in stmt.stmts:
                self.gen_stmt(s)
            return
        if isinstance(stmt, InlineAsm):
            self._emit_inline_asm(stmt)
            return
        if isinstance(stmt, If):
            self.gen_if(stmt)
            return
        if isinstance(stmt, While):
            self.gen_while(stmt)
            return
        if isinstance(stmt, For):
            self.gen_for(stmt)
            return
        if isinstance(stmt, Break):
            if not self.loop_stack:
                raise GenError("ループ外の break")
            brk, _ = self.loop_stack[-1]
            self.emiti(f"JPI     {brk}")
            return
        if isinstance(stmt, Continue):
            if not self.loop_stack:
                raise GenError("ループ外の continue")
            _, cont = self.loop_stack[-1]
            self.emiti(f"JPI     {cont}")
            return
        raise GenError(f"未対応の文: {stmt!r}")

    def _emit_inline_asm(self, stmt):
        for line in stmt.code.split('\n'):
            line = line.rstrip()
            if line.strip():
                self.emiti(line.strip())

    def _extract_inline_asm_builtin(self, func):
        """ゼロ引数で本体が単一 InlineAsm のみの関数なら、その asm 文字列を返す。

        該当しなければ None。呼び出し側 (Call) でこの asm を直接展開し、
        関数定義の emission はスキップする。MOVI R0, label のように
        callee-saved を壊さない 1 命令ラッパーを想定。
        """
        if func.params:
            return None
        stmts = []
        for s in func.body:
            if isinstance(s, list):
                stmts.extend(s)
            else:
                stmts.append(s)
        if len(stmts) != 1:
            return None
        s = stmts[0]
        if not isinstance(s, InlineAsm):
            return None
        return s.code

    def gen_if(self, stmt):
        else_label = self._new_label('else')
        end_label = self._new_label('endif')
        if stmt.else_ is None:
            self._gen_cond_branch(stmt.cond, end_label, jump_when_true=False)
            self.gen_stmt(stmt.then)
            self.emit(f"{end_label}:")
        else:
            self._gen_cond_branch(stmt.cond, else_label, jump_when_true=False)
            self.gen_stmt(stmt.then)
            self.emiti(f"JPI     {end_label}")
            self.emit(f"{else_label}:")
            self.gen_stmt(stmt.else_)
            self.emit(f"{end_label}:")

    def gen_while(self, stmt):
        start = self._new_label('while')
        end = self._new_label('endw')
        self.emit(f"{start}:")
        self._gen_cond_branch(stmt.cond, end, jump_when_true=False)
        self.loop_stack.append((end, start))
        self.gen_stmt(stmt.body)
        self.loop_stack.pop()
        self.emiti(f"JPI     {start}")
        self.emit(f"{end}:")

    def gen_for(self, stmt):
        start = self._new_label('for')
        cont = self._new_label('forc')
        end = self._new_label('endf')
        if stmt.init is not None:
            self.gen_expr(stmt.init)
        self.emit(f"{start}:")
        if stmt.cond is not None:
            self._gen_cond_branch(stmt.cond, end, jump_when_true=False)
        self.loop_stack.append((end, cont))
        self.gen_stmt(stmt.body)
        self.loop_stack.pop()
        self.emit(f"{cont}:")
        if stmt.update is not None:
            self.gen_expr(stmt.update)
        self.emiti(f"JPI     {start}")
        self.emit(f"{end}:")

    # ── 式 ────────────────────────────────────────────
    def gen_expr(self, e):
        if isinstance(e, IntLit):
            self._load_imm(e.value)
            return

        if isinstance(e, StringLit):
            label = f"_str_{len(self.string_pool)}"
            self.string_pool.append((label, e.data))
            self.emiti(f"MOVI    R0, {label}")
            return

        if isinstance(e, Sizeof):
            v = self._sizeof_type(e.target) if e.is_type else self._sizeof_expr(e.target)
            self._load_imm(v)
            return

        if isinstance(e, Var):
            t = self._lookup_type(e.name)
            if t.kind == 'array' or t.kind == 'struct':
                # 配列／struct はアドレスにディケイ（struct も V6 流に address のみ）
                self._load_var_addr(e.name)
                return
            self._load_from_var(e.name)
            return

        if isinstance(e, AddrOf):
            if isinstance(e.operand, Var):
                self._load_var_addr(e.operand.name)
                return
            if isinstance(e.operand, Deref):
                # &*x = x
                self.gen_expr(e.operand.operand)
                return
            if isinstance(e.operand, Member):
                # &(struct.m) のアドレスを R0 に
                self._gen_member_addr(e.operand)
                return
            raise GenError("& は変数か *式 か member にのみ適用可")

        if isinstance(e, Deref):
            ptype = self.type_of(e.operand)
            if not _is_ptr_like(ptype):
                raise GenError(f"非ポインタを *  でデリファレンス")
            self.gen_expr(e.operand)
            base = ptype.base
            if base.kind == 'char':
                self.emiti("LDB     R0, [R0]")
            elif base.kind in ('array', 'struct'):
                # アドレスのまま（既に R0 にある）
                pass
            else:
                self.emiti("LDD     R0, [R0]")
            return

        if isinstance(e, Member):
            self._gen_member_load(e)
            return

        if isinstance(e, UnaryOp):
            if e.op == '-':
                self.gen_expr(e.operand)
                self.emiti("MOV     R1, R0")
                self.emiti("MOVI    R0, 0")
                self.emiti("SUB     R0, R1")
                return
            if e.op == '!':
                self.gen_expr(e.operand)
                end = self._new_label('not')
                self.emiti("SBTI    R0, 0")
                self.emiti("MOVI    R0, 1")
                self.emiti(f"JPZI    {end}")
                self.emiti("MOVI    R0, 0")
                self.emit(f"{end}:")
                return
            if e.op == '~':
                self.gen_expr(e.operand)
                self.emiti("NOT     R0")
                return
            raise GenError(f"未対応の単項演算子: {e.op}")

        if isinstance(e, BinOp):
            if e.op in CMP_OPS:
                self._gen_compare(e)
                return
            if e.op == '&&':
                self._gen_and(e)
                return
            if e.op == '||':
                self._gen_or(e)
                return
            if e.op in ('+', '-'):
                self._gen_add_sub(e)
                return
            if e.op in ('<<', '>>'):
                self._gen_shift(e)
                return
            if self._try_const_rhs_binop(e):
                return
            self.gen_expr(e.left)
            self.emiti("PUSH    R0")
            self.gen_expr(e.right)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
            inst = BINOP_TO_INST.get(e.op)
            if inst is None:
                raise GenError(f"未対応の二項演算子: {e.op}")
            self.emiti(f"{inst:7} R0, R1")
            return

        if isinstance(e, Assign):
            self._gen_assign(e.target, e.value)
            return

        if isinstance(e, IncDec):
            self._gen_incdec(e)
            return

        if isinstance(e, Call):
            if not e.args and e.name in self.inline_asm_builtins:
                # ゼロ引数の inline-asm builtin: CALLI/RET を経由せず
                # 関数本体の asm を直接展開する。
                code = self.inline_asm_builtins[e.name]
                for line in code.split('\n'):
                    line = line.strip()
                    if line:
                        self.emiti(line)
                return
            for arg in reversed(e.args):
                self.gen_expr(arg)
                self.emiti("PUSH    R0")
            self.emiti(f"CALLI   {e.name}")
            if e.args:
                self.emiti(f"ADDI    SP, {4 * len(e.args)}")
            return

        raise GenError(f"未対応の式: {e!r}")

    # ── struct メンバアクセス ─────────────────────────
    def _gen_struct_addr(self, e):
        """e の struct のアドレスを R0 にロード。struct の Type を返す。"""
        if isinstance(e, Var):
            t = self._lookup_type(e.name)
            if t.kind != 'struct':
                raise GenError(f"struct でない: {e.name}")
            self._load_var_addr(e.name)
            return t
        if isinstance(e, Deref):
            ptype = self.type_of(e.operand)
            if ptype.kind != 'pointer' or ptype.base.kind != 'struct':
                raise GenError("struct* でない")
            self.gen_expr(e.operand)
            return ptype.base
        if isinstance(e, Member):
            outer_t = self._gen_struct_addr(e.object)
            moff, mtype = self._find_member(outer_t.name, e.name)
            if mtype.kind != 'struct':
                raise GenError("ネストした member が struct でない")
            if moff > 0:
                self.emiti(f"ADDI    R0, {moff}")
            return mtype
        raise GenError(f"struct アクセスの対象が不正: {e!r}")

    def _gen_member_addr(self, member):
        """Member ノードの value 位置のアドレスを R0 に置く。member の Type を返す。"""
        obj_t = self._gen_struct_addr(member.object)
        moff, mtype = self._find_member(obj_t.name, member.name)
        if moff > 0:
            self.emiti(f"ADDI    R0, {moff}")
        return mtype

    def _gen_member_load(self, member):
        """Member の値を R0 にロード（配列メンバはアドレスのまま）。"""
        mtype = self._gen_member_addr(member)
        # R0 = アドレス。型に応じて load。
        if mtype.kind == 'array' or mtype.kind == 'struct':
            # アドレスのまま
            return
        if mtype.kind == 'char':
            self.emiti("LDB     R0, [R0]")
        else:
            self.emiti("LDD     R0, [R0]")

    # ── 加減算（ポインタスケール対応） ────────────────
    def _gen_add_sub(self, e):
        lt = self.type_of(e.left)
        rt = self.type_of(e.right)
        l_ptr = _is_ptr_like(lt)
        r_ptr = _is_ptr_like(rt)

        if l_ptr and r_ptr:
            raise GenError("ポインタ同士の演算は未対応")

        if l_ptr or r_ptr:
            if l_ptr:
                ptr_expr, int_expr, ptr_type = e.left, e.right, lt
            else:
                if e.op != '+':
                    raise GenError("ポインタが右辺で減算は不可")
                ptr_expr, int_expr, ptr_type = e.right, e.left, rt
            elem = self._elem_size(ptr_type)

            # int_expr が IntLit で scaled 値が 20bit 即値範囲なら 1 命令
            if isinstance(int_expr, IntLit):
                scaled = int_expr.value * elem
                if 0 <= scaled <= IMM20_MAX:
                    self.gen_expr(ptr_expr)
                    if scaled != 0:
                        inst = 'ADDI' if e.op == '+' else 'SUBI'
                        self.emiti(f"{inst:7} R0, {scaled}")
                    return

            self.gen_expr(ptr_expr)
            self.emiti("PUSH    R0")
            self.gen_expr(int_expr)
            if elem != 1:
                self.emiti(f"MULI    R0, {elem}")
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
            self.emiti("ADD     R0, R1" if e.op == '+' else "SUB     R0, R1")
            return

        if self._try_const_rhs_binop(e):
            return

        self.gen_expr(e.left)
        self.emiti("PUSH    R0")
        self.gen_expr(e.right)
        self.emiti("MOV     R1, R0")
        self.emiti("POP     R0")
        inst = BINOP_TO_INST[e.op]
        self.emiti(f"{inst:7} R0, R1")

    def _try_const_rhs_binop(self, e):
        """e.right が IntLit で 20bit 即値範囲内なら即値版命令で評価。

        成功時 True を返す。`+,-,*,/,%,&,|,^` 用。ポインタ算術は呼び出し側で
        除外しておくこと。
        """
        if not isinstance(e.right, IntLit):
            return False
        inst_i = BINOP_TO_IMM_INST.get(e.op)
        if inst_i is None:
            return False
        v = e.right.value
        if not (0 <= v <= IMM20_MAX):
            return False
        self.gen_expr(e.left)
        self.emiti(f"{inst_i:7} R0, {v}")
        return True

    def _gen_shift(self, e):
        # 右辺が IntLit の定数シフトなら 1 命令 (MULI / DIVI 2^n) に畳む
        if isinstance(e.right, IntLit) and e.right.value >= 0:
            n = e.right.value
            self.gen_expr(e.left)
            if n == 0:
                return
            factor = 1 << n
            if factor <= IMM20_MAX:
                inst = 'MULI' if e.op == '<<' else 'DIVI'
                self.emiti(f"{inst:7} R0, {factor}")
                return
            # 即値範囲外は通常パスへフォールバック
            self.emiti("PUSH    R0")
            self._load_imm(n)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
        else:
            self.gen_expr(e.left)
            self.emiti("PUSH    R0")
            self.gen_expr(e.right)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
        start = self._new_label('sh')
        end = self._new_label('she')
        self.emit(f"{start}:")
        self.emiti("SBTI    R1, 0")
        self.emiti(f"JPZI    {end}")
        if e.op == '<<':
            self.emiti("MULI    R0, 2")
        else:
            self.emiti("DIVI    R0, 2")
        self.emiti("DEC     R1")
        self.emiti(f"JPI     {start}")
        self.emit(f"{end}:")

    # ── 代入 ──────────────────────────────────────────
    def _gen_assign(self, target, value_expr):
        if isinstance(target, Var):
            t = self._lookup_type(target.name)
            if t.kind in ('array', 'struct'):
                raise GenError(f"{t.kind} 型 {target.name} には代入できない")
            self.gen_expr(value_expr)
            self._store_to_var(target.name)
            return

        if isinstance(target, Deref):
            ptype = self.type_of(target.operand)
            if not _is_ptr_like(ptype):
                raise GenError("非ポインタへの代入")
            elem = ptype.base
            self.gen_expr(value_expr)
            self.emiti("PUSH    R0")
            self.gen_expr(target.operand)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
            if elem.kind == 'char':
                self.emiti("STB     R0, [R1]")
            else:
                self.emiti("STD     R0, [R1]")
            return

        if isinstance(target, Member):
            mtype = self._peek_member_type(target)
            if mtype.kind in ('array', 'struct'):
                raise GenError(f"{mtype.kind} 型 member には代入できない")
            self.gen_expr(value_expr)
            self.emiti("PUSH    R0")
            self._gen_member_addr(target)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
            if mtype.kind == 'char':
                self.emiti("STB     R0, [R1]")
            else:
                self.emiti("STD     R0, [R1]")
            return

        raise GenError(f"代入のターゲットが lvalue でない: {target!r}")

    def _peek_member_type(self, member):
        obj_t = self._struct_type_of(member.object)
        _, mtype = self._find_member(obj_t.name, member.name)
        return mtype

    # ── インクリメント／デクリメント ─────────────────
    def _gen_incdec(self, e):
        if not isinstance(e.operand, Var):
            raise GenError("++/-- は変数のみ（現状）")
        name = e.operand.name
        t = self._lookup_type(name)
        step = 1
        if t.kind == 'pointer':
            step = self._elem_size(t)
        self._load_from_var(name)
        if e.is_prefix:
            self._step(step, e.op)
            self._store_to_var(name)
        else:
            self.emiti("MOV     R3, R0")
            self._step(step, e.op)
            self._store_to_var(name)
            self.emiti("MOV     R0, R3")

    def _step(self, step, op):
        if step == 1:
            self.emiti("INC     R0" if op == '++' else "DEC     R0")
        else:
            instr = 'ADDI' if op == '++' else 'SUBI'
            self.emiti(f"{instr}    R0, {step}")

    # ── 比較 ──────────────────────────────────────────
    # 比較演算子ごとの分岐命令（true で飛ぶ／false で飛ぶ）
    _CMP_JUMP_TRUE = {
        '==': 'JPZI',  '!=': 'JPNZI',
        '<':  'JPUI',  '>=': 'JPNUI',
        '>':  'JPUI',  '<=': 'JPNUI',   # オペランド入れ替えで吸収
    }
    _CMP_JUMP_FALSE = {
        '==': 'JPNZI', '!=': 'JPZI',
        '<':  'JPNUI', '>=': 'JPUI',
        '>':  'JPNUI', '<=': 'JPUI',
    }

    def _gen_compare_branch(self, e, target, jump_when_true):
        """比較 e の結果に応じて target へ分岐。0/1 マテリアライズを省略。

        右辺が 20bit 即値 IntLit なら SBTI で 1 命令化（フェーズ B）。
        """
        swap = e.op in ('>', '<=')
        rhs_is_imm = (
            isinstance(e.right, IntLit)
            and 0 <= e.right.value <= IMM20_MAX
        )

        if rhs_is_imm and not swap:
            self.gen_expr(e.left)
            self.emiti(f"SBTI    R0, {e.right.value}")
        elif rhs_is_imm and swap:
            # `R0 > imm` は `imm < R0`。SBT R1, R0 にしたいので R1=imm。
            self.gen_expr(e.left)
            self.emiti(f"MOVI    R1, {e.right.value}")
            self.emiti("SBT     R1, R0")
        else:
            self.gen_expr(e.left)
            self.emiti("PUSH    R0")
            self.gen_expr(e.right)
            self.emiti("MOV     R1, R0")
            self.emiti("POP     R0")
            if swap:
                self.emiti("SBT     R1, R0")
            else:
                self.emiti("SBT     R0, R1")

        table = self._CMP_JUMP_TRUE if jump_when_true else self._CMP_JUMP_FALSE
        self.emiti(f"{table[e.op]:<8}{target}")

    def _gen_cond_branch(self, e, target, jump_when_true):
        """条件式 e を評価し、jump_when_true なら e が truthy のとき target へ分岐。
        Compare / && / || / ! は 0/1 マテリアライズを省略して直接分岐に縮約。
        """
        if isinstance(e, BinOp) and e.op in CMP_OPS:
            self._gen_compare_branch(e, target, jump_when_true)
            return
        if isinstance(e, BinOp) and e.op == '&&':
            if jump_when_true:
                # 両方 truthy のとき target。左 falsy なら以降スキップ。
                skip = self._new_label('andS')
                self._gen_cond_branch(e.left, skip, jump_when_true=False)
                self._gen_cond_branch(e.right, target, jump_when_true=True)
                self.emit(f"{skip}:")
            else:
                # どちらか falsy なら target。
                self._gen_cond_branch(e.left, target, jump_when_true=False)
                self._gen_cond_branch(e.right, target, jump_when_true=False)
            return
        if isinstance(e, BinOp) and e.op == '||':
            if jump_when_true:
                # どちらか truthy なら target。
                self._gen_cond_branch(e.left, target, jump_when_true=True)
                self._gen_cond_branch(e.right, target, jump_when_true=True)
            else:
                # 両方 falsy のとき target。左 truthy なら以降スキップ。
                skip = self._new_label('orS')
                self._gen_cond_branch(e.left, skip, jump_when_true=True)
                self._gen_cond_branch(e.right, target, jump_when_true=False)
                self.emit(f"{skip}:")
            return
        if isinstance(e, UnaryOp) and e.op == '!':
            self._gen_cond_branch(e.operand, target, not jump_when_true)
            return
        # フォールバック：値を R0 に出してから 0 と比較
        self.gen_expr(e)
        self.emiti("SBTI    R0, 0")
        if jump_when_true:
            self.emiti(f"JPNZI   {target}")
        else:
            self.emiti(f"JPZI    {target}")

    def _gen_compare(self, e):
        """比較を値として使う場面（R0 に 0/1 を残す）。"""
        false_label = self._new_label('cmpF')
        end = self._new_label('cmpE')
        self._gen_compare_branch(e, false_label, jump_when_true=False)
        self.emiti("MOVI    R0, 1")
        self.emiti(f"JPI     {end}")
        self.emit(f"{false_label}:")
        self.emiti("MOVI    R0, 0")
        self.emit(f"{end}:")

    def _gen_and(self, e):
        """a && b を値として使う場面（R0 に 0/1 を残す）。短絡評価。"""
        false_label = self._new_label('andF')
        end = self._new_label('andE')
        self._gen_cond_branch(e.left, false_label, jump_when_true=False)
        self._gen_cond_branch(e.right, false_label, jump_when_true=False)
        self.emiti("MOVI    R0, 1")
        self.emiti(f"JPI     {end}")
        self.emit(f"{false_label}:")
        self.emiti("MOVI    R0, 0")
        self.emit(f"{end}:")

    def _gen_or(self, e):
        """a || b を値として使う場面（R0 に 0/1 を残す）。短絡評価。"""
        true_label = self._new_label('orT')
        end = self._new_label('orE')
        self._gen_cond_branch(e.left, true_label, jump_when_true=True)
        self._gen_cond_branch(e.right, true_label, jump_when_true=True)
        self.emiti("MOVI    R0, 0")
        self.emiti(f"JPI     {end}")
        self.emit(f"{true_label}:")
        self.emiti("MOVI    R0, 1")
        self.emit(f"{end}:")

    # ── 低レベルヘルパ ────────────────────────────────
    def _load_imm(self, v):
        v = v & 0xFFFFFFFF
        if v <= 0xFFFFF:
            self.emiti(f"MOVI    R0, {v}")
        else:
            hi = (v >> 20) & 0xFFF
            lo = v & 0xFFFFF
            self.emiti(f"MOVI    R0, {hi}")
            self.emiti(f"MULI    R0, 0x100000")
            self.emiti(f"ORI     R0, {lo}")

    def _load_var_addr(self, name):
        """変数のアドレスを R0 に置く（local or global）。"""
        if name in self.local_offsets:
            off = self.local_offsets[name]
            self.emiti("MOV     R0, R7")
            if off > 0:
                self.emiti(f"ADDI    R0, {off}")
            elif off < 0:
                self.emiti(f"SUBI    R0, {-off}")
            return
        if name in self.globals:
            label = self.globals[name][0]
            self.emiti(f"MOVI    R0, {label}")
            return
        raise GenError(f"未定義の変数: {name}")

    def _load_from_var(self, name):
        """スカラ変数の値を R0 にロード。型に応じて LDB / LDD を使い分け。"""
        t = self._lookup_type(name)
        self._load_var_addr(name)
        if t.kind == 'char':
            self.emiti("LDB     R0, [R0]")
        else:
            self.emiti("LDD     R0, [R0]")

    def _store_to_var(self, name):
        """R0 の値をスカラ変数に格納。R0 は保持される。"""
        t = self._lookup_type(name)
        # アドレスを R2 に作る（R0 を壊さないように）
        if name in self.local_offsets:
            off = self.local_offsets[name]
            self.emiti("MOV     R2, R7")
            if off > 0:
                self.emiti(f"ADDI    R2, {off}")
            elif off < 0:
                self.emiti(f"SUBI    R2, {-off}")
        elif name in self.globals:
            label = self.globals[name][0]
            self.emiti(f"MOVI    R2, {label}")
        else:
            raise GenError(f"未定義の変数: {name}")
        if t.kind == 'char':
            self.emiti("STB     R0, [R2]")
        else:
            self.emiti("STD     R0, [R2]")


def generate(program):
    g = CodeGen()
    g.gen_program(program)
    return g.output()
