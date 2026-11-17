package org.example.game;

import java.awt.Point;
import java.awt.geom.Rectangle2D;

public class QualifiedNew {
    public Rectangle2D rect() {
        return new Rectangle2D.Float(0, 0, 1, 1);
    }

    public Object[] all() {
        Object a = new java.awt.Point(1, 2);
        Object b = new Point(3, 4);
        Object c = new Rectangle2D.Double();
        Object d = new Rectangle2D. Double();
        Object e = new java.util.ArrayList<String>();
        return new Object[] {a, b, c, d, e};
    }
}
