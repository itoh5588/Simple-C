struct pair {
    char c;
    int x;
};

int main() {
    int a[3];
    struct pair p;
    return sizeof(int) + sizeof(char) + sizeof(a) + sizeof(p);
}
