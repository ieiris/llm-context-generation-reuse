package apoMario.game.panels;

import apoMario.ApoMarioConstants;
import apoMario.entity.ApoMarioPlayer;
import apoMario.game.ApoMarioPanel;
import apoMario.level.ApoMarioLevel;
import org.apogames.ApoConstants;

public class IntegrationDriver {

    private final ApoMarioPanel game;
    private final ApoMarioLevel level;
    private final long seed;

    public IntegrationDriver(long seed) {
        ApoConstants.B_APPLET = true;
        this.seed = seed;
        this.game = new ApoMarioPanel();
        this.game.setBRepaint(false);
        this.game.setBThink(false);
        this.game.init();
        this.level = this.game.getLevel();
        this.level.makeLevel(seed, false, true, 40, 1);
        this.game.setGame(false);
    }

    public void resetLevel() {
        this.level.makeLevel(seed, false, true, 40, 1);
        this.game.setGame(false);
    }

    public ApoMarioPanel panel() { return game; }
    public ApoMarioLevel level() { return level; }
    public ApoMarioPlayer player() { return level.getPlayers().get(0); }

    public void step(int n) {
        for (int i = 0; i < n; i++) game.thinkLevelGame(ApoMarioConstants.WAIT_TIME_THINK);
    }


    public long elapsedMillis() {
        return Math.max(0, 76000L - level.getTime());
    }

    public void endRun() {
        level.setAnalysis(false);
        step(2);
    }
}
