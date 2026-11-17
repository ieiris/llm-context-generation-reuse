package org.example.game;

import java.io.InputStream;

public class ClassLiteralCall {
    public InputStream open(String s) {
        return ClassLiteralCall.class.getResourceAsStream(s);
    }

    public String names() {
        return String.class.getName() + int[].class.getName();
    }
}
