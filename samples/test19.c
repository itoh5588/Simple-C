/* struct と member */
struct Point {
    int x;
    int y;
};

int sum(struct Point *p) {
    return p->x + p->y;
}

int main() {
    struct Point pt;
    pt.x = 10;
    pt.y = 20;
    return sum(&pt);
}
/* 期待値: 30 */
