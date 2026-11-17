package org.example.game;

public class DuplicateAndOrder {
    static class Player {
        public void move() {
        }

        public void jump() {
        }
    }

    public void order(Player player, Player Zeta, Player beta, Player Alpha, Player _x) {
        player.move();
        player.move();
        Zeta.move();
        player.jump();
        beta.jump();
        Alpha.move();
        _x.move();
        player.move();
    }
}
