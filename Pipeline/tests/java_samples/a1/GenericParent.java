package org.example.util;

import java.util.ArrayList;

public class GenericParent extends ArrayList<String> implements Comparable<GenericParent> {
    public int compareTo(GenericParent other) {
        return 0;
    }
}
