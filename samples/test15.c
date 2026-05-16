/* 文字列リテラル、ポインタ算術 */
int strlen(char *s) {
    int n = 0;
    while (*s) {
        n = n + 1;
        s++;
    }
    return n;
}
int main() {
    return strlen("Hello, World!");
}
/* 期待値: 13 */
