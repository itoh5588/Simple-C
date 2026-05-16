/* K&R スタイル */
int max(a, b)
int a;
int b;
{
    if (a > b) return a;
    return b;
}
int main() {
    return max(42, 17);
}
/* 期待値: 42 */
