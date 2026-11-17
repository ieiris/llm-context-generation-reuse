package org.example.game;

public class DeprecatedMethod {
    @Deprecated
    public void old() {
    }

    @Override
    @Deprecated
    public String toString() {
        return "deprecated";
    }

    public void current() {
    }
}
