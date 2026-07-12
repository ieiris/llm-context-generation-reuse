package apoMario.game.panels;

import org.junit.Test;
import org.junit.Before;
import org.junit.BeforeClass;
import static org.junit.Assert.*;
import java.lang.reflect.Field;
import apoMario.entity.ApoMarioPlayer;


public class ApoMarioHighscoreWiringTest {

    private static IntegrationDriver d;
    private ApoMarioPlayer p;

    @BeforeClass public static void boot() { d = new IntegrationDriver(12345L); }
    @Before public void reset() { d.resetLevel(); p = d.player(); }

    private ApoMarioHighscore locate() {
        Object hit = scan(d.panel(), 2);
        if (hit == null) hit = scan(d.level(), 1);
        if (hit == null) hit = scanStatics(ApoMarioHighscore.class);
        assertNotNull("no live ApoMarioHighscore instance reachable from the running game "
                + "(searched panel/level fields and class statics) — feature state is not connected",
                hit);
        return (ApoMarioHighscore) hit;
    }
    private Object scan(Object root, int depth) {
        if (root == null || depth < 0) return null;
        for (Class<?> c = root.getClass(); c != null; c = c.getSuperclass()) {
            for (Field f : c.getDeclaredFields()) {
                try {
                    f.setAccessible(true);
                    Object v = f.get(root);
                    if (v instanceof ApoMarioHighscore) return v;
                    if (v != null && depth > 0 && v.getClass().getName().startsWith("apoMario")) {
                        Object deep = scan(v, depth - 1);
                        if (deep != null) return deep;
                    }
                } catch (Exception ignored) { }
            }
        }
        return null;
    }
    private Object scanStatics(Class<?> cls) {
        for (Field f : cls.getDeclaredFields()) {
            try {
                f.setAccessible(true);
                Object v = f.get(null);
                if (v instanceof ApoMarioHighscore) return v;
            } catch (Exception ignored) { }
        }
        return null;
    }

    @Test public void runEndRecordsScoreWithoutHelp() {
        p.setPoints(54321);
        p.setTeamName("wiretest");
        d.endRun();
        ApoMarioHighscore h = locate();
        assertTrue("ending a run must make the GAME record the score by itself (no test call); scores="
                + h.getPlayersScores(), h.getPlayersScores().contains(Integer.valueOf(54321)));
    }

    @Test public void recordedNameIsTheRealPlayersName() {
        p.setPoints(777);
        p.setTeamName("Luigi");
        d.endRun();
        ApoMarioHighscore h = locate();
        int i = h.getPlayersScores().indexOf(Integer.valueOf(777));
        assertTrue("the 777-point run must be on the board; scores=" + h.getPlayersScores(), i >= 0);
        assertEquals("the recorded name must be the player's real getTeamName(); names="
                + h.getPlayersNames(), "Luigi", h.getPlayersNames().get(i));
    }

    @Test public void noPhantomEntriesWithoutRunEnd() {
        p.setPoints(99999);
        d.step(5);
        Object h = scan(d.panel(), 2);
        if (h == null) h = scanStatics(ApoMarioHighscore.class);
        if (h != null)
            assertFalse("merely playing (no run end) must not add board entries; scores="
                    + ((ApoMarioHighscore) h).getPlayersScores(),
                    ((ApoMarioHighscore) h).getPlayersScores().contains(Integer.valueOf(99999)));
    }
    @Test public void recordedSurvivalTimeIsTheRealElapsedTime() {
        p.setPoints(31337);
        d.step(30);
        int before = d.level().getPassedTime();
        d.endRun();
        int after = d.level().getPassedTime();
        ApoMarioHighscore h = locate();
        int i = h.getPlayersScores().indexOf(Integer.valueOf(31337));
        assertTrue("the 31337-point run must be on the board; scores=" + h.getPlayersScores(), i >= 0);
        int t = h.getSurvivalTimes().get(i);
        assertTrue("recorded survival time must be the run's real elapsed time (between " + before
                + " and " + after + "ms), not 0 or a wall-clock value; got " + t,
                t >= before && t <= after);
    }
    @Test public void secondRunAlsoRecordedAndBoardSortedDescending() {
        p.setPoints(9100);
        d.endRun();
        d.resetLevel();
        d.player().setPoints(9900);
        d.endRun();
        ApoMarioHighscore h = locate();
        int lo = h.getPlayersScores().indexOf(Integer.valueOf(9100));
        int hi = h.getPlayersScores().indexOf(Integer.valueOf(9900));
        assertTrue("both runs must be on the board; scores=" + h.getPlayersScores(), lo >= 0 && hi >= 0);
        assertTrue("the live board must keep descending order (9900 before 9100); scores="
                + h.getPlayersScores(), hi < lo);
    }
}
