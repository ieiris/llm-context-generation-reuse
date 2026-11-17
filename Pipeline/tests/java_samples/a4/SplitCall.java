package org.example.game;

import java.awt.Image;
import java.util.ArrayList;
import java.util.List;

public class SplitCall {
    private List<String> list = new ArrayList<String>();

    public int split(Image image) {
        int h = image
                .getHeight(null);
        int w = image .getWidth(null);
        int s = list./* size */size();
        list.<String>toArray(new String[0]);
        int q = list.size ();
        return h + w + s + q + list.indexOf("a");
    }
}
