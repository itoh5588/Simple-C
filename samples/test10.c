/* 関数呼び出し（ANSI スタイル） */
int add(int a, int b) {
    return a + b;
}
int main() {
    return add(3, 4) + add(10, 20);
}
/* 期待値: 7 + 30 = 37 */
