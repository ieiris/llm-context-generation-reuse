package org.example.game;

public class Numbers {
    public int dedup() {
        int a = 50;
        int b = 10 + 50 + 300;
        return a + b;
    }

    public double decimals() {
        double c = 1000.0;
        double d = 0.25;
        double e = 0.004;
        return c + d + e;
    }

    public long suffixes() {
        float f = 100f;
        long g = 10L;
        int h = 0x10;
        int i = 010;
        int k = 1_000;
        return (long) f + g + h + i + k;
    }

    public String signs() {
        int j = -100;
        long big = 123456;
        char ch = '7';
        return "200" + j + big + ch;
    }

    public int firstSix() {
        return 11 + 22 + 33 + 44 + 55 + 66 + 77 + 11;
    }
}
