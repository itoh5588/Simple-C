"""コンパイル済みバイナリを単体実行するテストランナー（OS無し）

使い方: python test_run.py <file.bin>

main の RET 先として HALT 命令を 0xC0000 に置き、SP に push しておくことで、
プログラムは正常終了時に HALT に飛んで停止する。最後にレジスタダンプが出る。
"""
import sys
import emu


def run_binary(path):
    with open(path, 'rb') as f:
        prog = f.read()
    if len(prog) > 0xC0000:
        print("プログラムが大きすぎます", file=sys.stderr)
        sys.exit(1)

    # ユーザープログラムは PC=0 から始まる前提
    emu.memory[0:len(prog)] = prog
    # 戻り先トランポリン: 0xC0000 に HALT (type0=0, op=1 → 0x01000000)
    emu.memory[0xC0000:0xC0000+4] = bytes([0x01, 0x00, 0x00, 0x00])

    emu.registers['PC'] = 0
    emu.registers['SP'] = 0xBF000
    # main からの RET 先として HALT のアドレスを積む
    emu.push(0xC0000)

    # 出力を抑制（テスト用）。HALT 時の print_registers だけは見たいので置換しない
    emu.run()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_run.py <file.bin>", file=sys.stderr)
        sys.exit(1)
    run_binary(sys.argv[1])
