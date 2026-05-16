/* #define マクロ */
#define MAX 100
#define DOUBLE(x) (x*2)   /* 関数マクロは未対応のためテキスト置換は単純 */

int main() {
    int n = MAX;
    return n / 2;
}
/* 期待値: 50 */
