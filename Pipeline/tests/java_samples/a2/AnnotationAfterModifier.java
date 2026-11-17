package org.example.game;

public class AnnotationAfterModifier {
    @Deprecated private int before;
    private @Deprecated int after;
    public @Deprecated static final int OLD_LIMIT = 3;
}
