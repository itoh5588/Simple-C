int cmp_str_c(char *a, char *b) {
    while (*a == *b) {
        if (*a == 0) {
            return 0;
        }
        a++;
        b++;
    }
    return 1;
}

int get_nth_token_c(int n, char *input) {
    char *p;
    char *start;
    char *out;
    int in_token;
    int c;

    p = input;
    start = 0;
    out = 0xC1000;
    in_token = 0;

    while (n > 0) {
        while (1) {
            c = *p;
            if (c == 0) {
                *out = 0;
                return 0xC1000;
            }
            if (c == 9 || c == 32) {
                if (in_token) {
                    in_token = 0;
                }
                p++;
                continue;
            }
            if (!in_token) {
                in_token = 1;
                start = p;
                break;
            }
            p++;
        }
        n--;
    }

    while (1) {
        c = *start;
        *out = c;
        if (c == 9 || c == 32 || c == 0) {
            *out = 0;
            return 0xC1000;
        }
        out++;
        start++;
    }
}

int main() {
    char *t;
    int ok;

    ok = 0;
    ok = ok + (cmp_str_c("exec", "exec") != 0);
    ok = ok + ((cmp_str_c("exec", "exit") == 0) << 1);

    t = get_nth_token_c(1, "taskexec foo 1");
    ok = ok + (!(t[0] == 't' && t[1] == 'a' && t[7] == 'c' && t[8] == 0) << 2);

    t = get_nth_token_c(2, "taskexec foo 1");
    ok = ok + (!(t[0] == 'f' && t[1] == 'o' && t[2] == 'o' && t[3] == 0) << 3);

    t = get_nth_token_c(3, "taskexec foo 1");
    ok = ok + (!(t[0] == '1' && t[1] == 0) << 4);

    t = get_nth_token_c(2, "  exec   hello.bin");
    ok = ok + (!(t[0] == 'h' && t[5] == '.' && t[8] == 'n' && t[9] == 0) << 5);

    t = get_nth_token_c(3, "exec");
    ok = ok + (!(t[0] == 0) << 6);

    return ok;
}
