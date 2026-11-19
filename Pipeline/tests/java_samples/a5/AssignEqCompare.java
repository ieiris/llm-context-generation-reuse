package org.example.game;

public class AssignEqCompare {
    private int state;
    private int other;

    public boolean check(int s) {
        if (this.state == s) {
            return true;
        }
        return this.other != s;
    }

    public void step() {
        if (this.state <= 20) {
            this.state += 1;
        }
    }
}
