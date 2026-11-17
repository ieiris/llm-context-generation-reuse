package org.example.game;

public class Constants {
    public static final int MAX = 100;
    public static final String NAME = "ApoGame";
    public static final int[] SIZES = {16, 32, 64};
    public static final int X = 5;
    public static final String LONG_TEXT = "This value is longer than sixty characters, so it is cut off";
    public static final String MULTI_LINE =
        "first part, " +
        "second part";
    public final static int ORDER = 1;
    private static final int HIDDEN = 2;
    public static final int NO_INIT;
    public static final String SEP = "a;b";

    static {
        NO_INIT = 7;
    }
}
