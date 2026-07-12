package apoMario.game.panels;

import org.junit.Test;
import org.junit.Before;
import org.junit.BeforeClass;
import static org.junit.Assert.*;
import java.nio.file.Files;
import apoMario.entity.ApoMarioPlayer;

public class ApoMarioHighscoreCouplingTest {

    private static IntegrationDriver d;
    private ApoMarioPlayer p;

    @BeforeClass public static void boot() { d = new IntegrationDriver(12345L); }
    @Before public void reset() { p = d.player(); p.setPoints(0); p.setTeamName("tester"); }

    private ApoMarioHighscore fresh() throws Exception {
        return new ApoMarioHighscore(Files.createTempDirectory("hs").resolve("hs.dat"));
    }

    @Test public void recordsRealScore() throws Exception {
        p.setPoints(54321);
        ApoMarioHighscore h = fresh(); h.recordRunEnd(d.level());
        assertEquals("recordRunEnd must record the player's real getPoints(); scores=" + h.getPlayersScores(),
                Integer.valueOf(54321), h.getPlayersScores().get(0));
    }
    @Test public void recordsRealSurvivalTime() throws Exception {
        d.step(50);
        int expected = d.level().getPassedTime();
        ApoMarioHighscore h = fresh(); h.recordRunEnd(d.level());
        assertEquals("recordRunEnd must record level.getPassedTime() (elapsed), NOT getTime(); times="
                + h.getSurvivalTimes(), Integer.valueOf(expected), h.getSurvivalTimes().get(0));
    }
    @Test public void recordsRealPlayerName() throws Exception {
        p.setTeamName("Mario");
        ApoMarioHighscore h = fresh(); h.recordRunEnd(d.level());
        assertEquals("recordRunEnd must record the player's real getTeamName(); names=" + h.getPlayersNames(),
                "Mario", h.getPlayersNames().get(0));
    }
    @Test public void recordRunEndAddsExactlyOneEntry() throws Exception {
        p.setPoints(100);
        ApoMarioHighscore h = fresh(); h.recordRunEnd(d.level());
        assertEquals("one run-end must add exactly one board entry; names=" + h.getPlayersNames(),
                1, h.getPlayersNames().size());
    }
}
