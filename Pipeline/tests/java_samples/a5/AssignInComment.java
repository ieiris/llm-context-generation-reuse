package org.example.game;

public class AssignInComment {
    private int width;
    private int height;

    public void resize(int w, int h) {
        // this.width = 640;
        /* this.height = 480; */
        this.width = w;
        this.height = h; // was 200
    }
}
