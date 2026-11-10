package org.example.ui;

import java.awt.event.KeyListener;
import java.awt.event.MouseListener;
import javax.swing.JComponent;

public abstract class MultilineImplements extends JComponent implements
        MouseListener, KeyListener {

    public abstract void init();
}
