package org.example.game;

public class AnonymousSelf {
    public AnonymousSelf() {
    }

    public static AnonymousSelf create() {
        return new AnonymousSelf() {
            @Override
            public String toString() {
                return "anonymous";
            }
        };
    }
}
