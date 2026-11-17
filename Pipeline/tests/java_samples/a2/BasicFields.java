package org.example.game;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class BasicFields {
    private int score;
    protected String playerName = "Apo";
    public boolean running;
    private final double speed = 1.5;
    private static int instances;
    private List<String> names = new ArrayList<String>();
    private Map<String, Integer> counts;
    private int[] levels;
    protected String[][] grid;
    private java.awt.Color background;
    int packagePrivate;

    public BasicFields() {
        int local = 5;
        score = local;
    }
}
