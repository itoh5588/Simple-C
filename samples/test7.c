/* if/else と比較 */
int main() {
    int a = 7;
    int b;
    if (a > 5) {
        b = 100;
    } else {
        b = 200;
    }
    if (a == 7)
        b = b + 1;
    return b;
}
/* 期待値: 101 */
