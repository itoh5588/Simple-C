/* int 配列、ポインタ算術（要素サイズ4） */
int main() {
    int a[4];
    int *p;
    int i;
    for (i = 0; i < 4; i++) a[i] = i * 10;
    p = a;
    p = p + 2;
    return *p + a[3];
}
/* 期待値: a[2] + a[3] = 20 + 30 = 50 */
