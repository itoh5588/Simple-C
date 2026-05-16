/* for ループ、break、continue、論理演算 */
int main() {
    int i;
    int sum = 0;
    for (i = 0; i < 20; i = i + 1) {
        if (i == 5) continue;
        if (i >= 15) break;
        if (i > 2 && i < 10) sum = sum + i;
    }
    /* sum = 3 + 4 + 6 + 7 + 8 + 9 = 37 */
    return sum;
}
/* 期待値: 37 */
