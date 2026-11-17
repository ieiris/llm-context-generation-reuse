package org.example.game;

public class NestedAndAnonymous {
    private int count;
    private String label;

    private static class Node {
        private long count;
        private Node next;
        public static final int LIMIT = 8;
    }

    enum Mode {
        EASY, HARD;
        private int level;
    }

    public void start() {
        Runnable task = new Runnable() {
            private int ticks;
            public void run() {
                ticks++;
            }
        };
        class Local {
            protected boolean done;
        }
        task.run();
    }
}
