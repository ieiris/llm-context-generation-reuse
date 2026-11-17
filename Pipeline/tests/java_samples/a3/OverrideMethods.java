package org.example.game;

public class OverrideMethods implements Runnable, Comparable<OverrideMethods> {
    @Override
    public void run() {
    }

    @Override
    public int compareTo(OverrideMethods other) {
        return 0;
    }

    @Override public String toString() {
        return "override";
    }

    public void plain() {
    }
}
