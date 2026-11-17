package org.example.game;

import java.util.ArrayList;
import java.util.List;

public class SuppressWarningsMethod {
    private List<String> names = new ArrayList<String>();

    @SuppressWarnings("unchecked")
    public List<String> copy() {
        return (List<String>) ((ArrayList<String>) names).clone();
    }

    @SuppressWarnings({"rawtypes", "unused"})
    private void raw() {
        List list = new ArrayList();
    }
}
