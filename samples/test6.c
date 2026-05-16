/* ++/-- 前置・後置 */
int main() {
    int a = 5;
    int b;
    b = a++;   /* b=5, a=6 */
    a = a + b; /* a=11 */
    --a;       /* a=10 */
    return a;
}
/* 期待値: 10 */
