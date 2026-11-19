package org.example.game;

public class AssignBasic {
    private int score;
    protected String name;
    public boolean alive;
    int hidden;
    private int x;

    public AssignBasic(String name) {
        this.name = name;
        this.score = 0;
        this.hidden = 5;
        this.x = 1;
    }

    public void reset(int start) {
        int local = 10;
        score = start;
        this.alive = true;
        this.score = local + start * 2;
    }

    public int getScore() {
        return this.score;
    }
}
