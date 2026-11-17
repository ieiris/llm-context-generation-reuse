package org.example.game;

public class NestedCalls {
    private Runnable task = new Runnable() {
        public void run() {
            helper.tick();
        }
    };
    private Helper helper = new Helper();

    public void start(final Helper h) {
        Thread t = new Thread() {
            @Override
            public void run() {
                h.tick();
                NestedCalls.this.stop();
            }
        };
        class Local {
            public int value() {
                return h.count();
            }
        }
        Runnable r = () -> h.reset();
        t.start();
    }

    public void stop() {
    }

    static class Helper {
        public void tick() {
            Thread.yield();
        }

        public int count() {
            return 0;
        }

        public void reset() {
        }
    }
}
