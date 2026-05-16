/* インラインアセンブリ。アセンブラのメモリアクセスは [Rn] のみ */
int main() {
    int x = 100;
    asm("MOV     R1, R7");
    asm("SUBI    R1, 4");      /* x のアドレス */
    asm("LDD     R0, [R1]");
    asm("ADDI    R0, 23");
    asm("STD     R0, [R1]");
    return x;
}
/* 期待値: 123 */
