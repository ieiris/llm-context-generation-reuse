package org.example.game;

public class BraceInString {
    private StringBuilder sb = new StringBuilder();

    public void open() {
        sb.append('{');
        sb.append("{{");
    }

    public void close() {
        sb.append("}");
        sb.reverse();
    }

    public void last() {
        sb.setLength(0);
    }
}
