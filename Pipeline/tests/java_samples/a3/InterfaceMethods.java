package org.example.game;

public interface InterfaceMethods {
    /** Plain interface method: implicitly abstract, not found (B1). */
    void start();

    /** Explicitly abstract. */
    public abstract int score();

    abstract void stop();

    /** Default method with a body. */
    default void reset() {
        stop();
    }

    static int version() {
        return 1;
    }
}
