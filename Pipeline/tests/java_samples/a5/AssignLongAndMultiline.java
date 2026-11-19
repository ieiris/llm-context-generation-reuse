package org.example.game;

public class AssignLongAndMultiline {
    private String message;
    private int total;
    private int count;

    public void build(int a, int b, int c) {
        this.message = "a very long message that is longer than sixty characters for sure";
        this.total = a +
                b + c;
        this.count =
                a * 100;
    }

    public void ifAssign() {
        if ((this.count = this.total) > 0) {
            this.total = 0;
        }
    }
}
