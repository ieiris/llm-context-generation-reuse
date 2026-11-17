package org.example.game;

public class Assets {
    private String player = "images/player.png";
    private String[] sounds = {"sounds/jump.wav", "sounds/coin.mp3"};

    public void load() {
        open("images/player.png");
        open("fonts/main.ttf");
        open("images/" + "tiles.gif");
        open("photo.jpg");
        open("UPPER.PNG");
        open("note.txt");
        open("say \"quoted.png\"");
    }

    private void open(String path) {
    }
}
