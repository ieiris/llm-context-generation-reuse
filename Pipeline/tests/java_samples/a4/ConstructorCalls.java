package org.example.game;

public class ConstructorCalls extends Thread {
    private final StringBuilder log;

    public ConstructorCalls() {
        this(new StringBuilder());
        log.append("default");
    }

    public ConstructorCalls(StringBuilder log) {
        super("worker");
        this.log = log;
        log.append(getName());
        setDaemon(true);
    }

    @Override
    public void run() {
        super.run();
        log.setLength(0);
    }
}
