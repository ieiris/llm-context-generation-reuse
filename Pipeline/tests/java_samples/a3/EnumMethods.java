package org.example.game;

public enum EnumMethods {
    EASY(1), HARD(3);

    private final int level;

    EnumMethods(int level) {
        this.level = level;
    }

    public int getLevel() {
        return level;
    }
}
