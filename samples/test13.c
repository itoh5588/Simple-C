/* ポインタの基本 (&, *) */
int main() {
    int x = 42;
    int *p;
    p = &x;
    *p = *p + 100;
    return x;
}
/* 期待値: 142 */
