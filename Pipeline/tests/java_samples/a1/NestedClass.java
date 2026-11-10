package org.example.game;

public class NestedClass {

    private Worker worker;

    class Worker extends Thread implements Runnable {
        public void run() {
        }
    }
}
