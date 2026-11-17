package org.example.game;

import java.io.IOException;

public class Constructors {
    private int a;

    /** No arguments. */
    public Constructors() {
    }

    /** Protected one. */
    protected Constructors(int a) throws IOException, IllegalStateException {
        this.a = a;
    }

    /** Private one. */
    private Constructors(int a, int b) {
        this.a = a + b;
    }

    Constructors(String s, int a, int b) {
    }
}
