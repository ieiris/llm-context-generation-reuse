package org.example.game;

public class NestedAndAnonymousMethods {
    private Runnable task = new Runnable() {
        public void run() {
        }
    };

    public NestedAndAnonymousMethods() {
    }

    public void start() {
        Thread t = new Thread() {
            @Override
            public void run() {
                tick();
            }
        };
        class Local {
            public int value() {
                return 1;
            }
        }
        t.start();
    }

    static class Helper {
        public void tick() {
        }
    }

    public void tick() {
    }
}
