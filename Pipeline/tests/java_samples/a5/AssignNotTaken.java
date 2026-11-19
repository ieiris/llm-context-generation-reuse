package org.example.game;

import java.awt.Point;

public class AssignNotTaken {
    private int count;
    private int[] cells = new int[16];
    private Point pos = new Point();

    public void update(AssignNotTaken other) {
        this.count += 20;
        this.count++;
        this.cells[0] = 1;
        this.pos.x = 3;
        other.count = 4;
        count = 5;
    }
}
