package org.example.game;

public class LineCommentBeforeMethod {
    private int score;

    // resets the score
    public void reset() {
        score = 0;
    }

    public int getScore() { // trailing comment
        return score;
    }

    /* block comment */ public void block() {
    }
}
