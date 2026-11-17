package org.example.game;

import java.awt.Graphics2D;

public abstract class AbstractAfterConcrete {
    /** Renders with defaults. */
    public void render() {
        render(null);
    }

    public void update() {
    }

    /** Renders on g. */
    public abstract void render(Graphics2D g);
}
