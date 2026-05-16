int main() {
    int x;
    x = (0x12 & 0x0f) | 0x20;
    x = x ^ 0x03;
    x = x << 2;
    x = x >> 1;
    return ~x & 0xff;
}
