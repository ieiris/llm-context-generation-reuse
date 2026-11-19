package org.example.game;

public class AssignOuterThis {
    private boolean running;
    private int rounds;

    public void start() {
        Thread t = new Thread() {
            public void run() {
                AssignOuterThis.this.running = true;
                AssignOuterThis.this.rounds = 10;
            }
        };
        t.start();
    }
}
