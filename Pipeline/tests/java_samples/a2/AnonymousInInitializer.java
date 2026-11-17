package org.example.game;

public class AnonymousInInitializer {
    private Runnable task = new Runnable() {
        private int counter;
        public void run() {
            counter++;
        }
    };
    private int after;
}
