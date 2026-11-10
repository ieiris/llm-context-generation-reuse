package org.example.game;

import java.awt.event.KeyListener;

public abstract class AbstractChild extends Base implements Runnable, KeyListener {
    public abstract void tick();
}
