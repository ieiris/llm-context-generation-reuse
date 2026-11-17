package org.example.game;

public abstract class OverloadAndAbstractCalls {
    private StringBuilder sb = new StringBuilder();

    public OverloadAndAbstractCalls() {
        sb.append("a");
    }

    public OverloadAndAbstractCalls(String s) {
        sb.append(s.trim());
    }

    public OverloadAndAbstractCalls(int n) {
        sb.setLength(n);
    }

    public void add(String s) {
        sb.append(s);
    }

    public void add(int n) {
        sb.insert(0, n);
    }

    public void render() {
        sb.reverse();
    }

    public abstract void render(int mode);
}
