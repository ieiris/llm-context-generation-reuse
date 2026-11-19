package org.example.game;

public class BodyEnd {
    private int level;

    public void think() {
        //if (level > 0) {
        this.level = 1;
    }

    public void render() {
        this.level = 42;
    }
}
