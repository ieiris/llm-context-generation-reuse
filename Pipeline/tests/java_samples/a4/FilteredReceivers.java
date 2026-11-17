package org.example.game;

public class FilteredReceivers {
    private String self = "s";

    public int filtered(Object o, Integer i, Boolean b, String s) {
        int m = Math.max(1, 2);
        System.gc();
        String v = String.valueOf(m);
        int p = Integer.parseInt(v);
        boolean q = Boolean.parseBoolean(v);
        int h = self.length();
        int k = s.length();
        Math.abs(o.hashCode());
        return m + p + h + k + (q ? 1 : 0) + i.intValue() + (b.booleanValue() ? 1 : 0);
    }

    public int objectVariable() {
        String Object = "x";
        return Object.length();
    }
}
