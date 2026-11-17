package org.example.game;

public enum EnumFields {
    SMALL(1), LARGE(2);

    private final int size;
    public static final String UNIT = "px";

    EnumFields(int size) {
        this.size = size;
    }
}
