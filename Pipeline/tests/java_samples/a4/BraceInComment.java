package org.example.game;

public class BraceInComment {
    private int x;
    private StringBuilder sb = new StringBuilder();

    public void close() {
        /* } */
        sb.trimToSize();
    }

    public void think() {
        //if (x > 0) {
        sb.append(x);
    }

    public void render() {
        sb.reverse();
    }

    public void reset() {
        sb.setLength(0);
    }
}
