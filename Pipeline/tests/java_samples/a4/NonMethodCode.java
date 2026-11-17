package org.example.game;

import java.util.HashMap;
import java.util.Map;

public class NonMethodCode {
    private static final Map<String, String> MAP = new HashMap<String, String>();
    private int size = Integer.valueOf(3).intValue();
    private String name = String.valueOf(size).trim();

    static {
        MAP.put("a", "b");
    }

    {
        size = MAP.size() + name.length();
    }

    public int size() {
        return size;
    }
}
