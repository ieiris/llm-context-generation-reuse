package org.example.game;

import java.awt.Graphics2D;

public abstract class AbstractMethods {
    /** Draws the thing. */
    public abstract void render(Graphics2D g);

    /** Updates by delta. */
    protected abstract boolean update(long delta);

    abstract int score();

    public void tick() {
        update(16);
    }
}
