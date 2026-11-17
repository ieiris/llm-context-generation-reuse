package org.example.game;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public abstract class GenericMethods {
    public <T> T first(List<T> items) {
        return items.get(0);
    }

    public static <K, V> Map<K, V> mapOf(K key, V value) {
        Map<K, V> map = new HashMap<K, V>();
        map.put(key, value);
        return map;
    }

    protected Map<String, List<Integer>> table(Map<String,Integer> seed, int n) {
        return null;
    }

    public abstract <T> T create(Class<T> type);
}
