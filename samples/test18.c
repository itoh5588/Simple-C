/* グローバル変数 */
int counter = 0;
char letter = 'A';

int incr() {
    counter = counter + 1;
    return counter;
}

int main() {
    incr();
    incr();
    incr();
    return counter + letter;
}
/* 期待値: 3 + 65 = 68 */
