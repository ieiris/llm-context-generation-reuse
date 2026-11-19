package org.example.game;

public class AssignConsumed {
    private int first;
    private int second;
    private int step;
    int tmp;

    public boolean inRange() {
        return (this.step == 5) || (this.step == 6) || (this.step == 7);
    }

    public void chain() {
        this.first = this.second = 0;
    }

    public boolean unknownFirst() {
        return this.tmp == 1 && this.first == 2;
    }
}
