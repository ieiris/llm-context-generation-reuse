package org.example.game;

public class AssignInString {
    private String help;
    private String code;

    public void init() {
        log("this.code = 42");
        this.code = "x;y";
    }

    private void log(String s) {
        this.help = s;
    }
}
