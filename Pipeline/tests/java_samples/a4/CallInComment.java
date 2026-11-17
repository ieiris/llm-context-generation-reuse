package org.example.game;

import java.util.ArrayList;
import java.util.List;

public class CallInComment {
    private List<String> items = new ArrayList<String>();

    public void clean() {
        // items.clear();
        /* old.remove(1); */
        /** debug.dump(items); */
        items.add("x");
    }

    public int count() {
        //System.out.println(items.size());
        return items.size();
    }
}
