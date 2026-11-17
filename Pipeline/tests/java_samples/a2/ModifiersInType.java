package org.example.game;

public class ModifiersInType {
    private volatile boolean running;
    private transient int cache;
    private final static int ORDER_FS = 1;
    final private int finalFirst = 2;
    static private final int staticFirst = 3;
    private static transient int staticTransient;
    private static volatile long ticks;
}
