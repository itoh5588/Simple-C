/* putchar, printd の連携 */
int main() {
    int i;
    puts("Sum 1..10 = ");
    int sum = 0;
    for (i = 1; i <= 10; i++) sum = sum + i;
    printd(sum);
    putchar('\n');
    return sum;
}
