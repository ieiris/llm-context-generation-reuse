package org.example.game;

public class OverloadedMethods {
    private int x;

    /** Creates an empty one. */
    public OverloadedMethods() {
        this(0);
    }

    /** Creates one at x. */
    public OverloadedMethods(int x) {
        this.x = x;
    }

    /** Creates one from a label (same arity: overwrites the one above). */
    protected OverloadedMethods(String label) {
        this.x = label.length();
    }

    /** Moves by dx. */
    public void move(int dx) {
        x += dx;
    }

    public int size() {
        return x;
    }

    /** Moves by dx and dy. */
    public void move(int dx, int dy) {
        x += dx + dy;
    }
}
