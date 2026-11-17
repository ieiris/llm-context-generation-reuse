package org.example.game;

public class BraceInBody {
    public char open() {
        return '{';
    }

    public String close() {
        return "}";
    }

    public String both() {
        String s = "{ ) (";
        return s + '}';
    }

    public void after() {
    }
}
