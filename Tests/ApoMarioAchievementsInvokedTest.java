package apoMario.game.panels;

import org.junit.Test;
import org.junit.Before;
import org.junit.BeforeClass;
import static org.junit.Assert.*;
import java.util.List;
import java.nio.file.Files;
import java.nio.file.Path;
import apoMario.entity.ApoMarioPlayer;


public class ApoMarioAchievementsCouplingTest {

    private static IntegrationDriver d;
    private ApoMarioPlayer p;

    @BeforeClass public static void boot() { d = new IntegrationDriver(12345L); }
    @Before public void reset() { p = d.player(); p.setPoints(0); }

    private ApoMarioStateAchievements fresh() throws Exception {
        return new ApoMarioStateAchievements(Files.createTempDirectory("ach").resolve("a.dat"));
    }
    private long count(List<String> l, String id) { long c = 0; for (String s : l) if (id.equals(s)) c++; return c; }

    @Test public void pointsGoalUnlocksAtThreshold() throws Exception {
        p.setPoints(20000);
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.recordRunEnd(d.level());
        assertTrue("20000 real points must unlock POINTS_GOAL (reads getPoints); got " + a.getUnlockedAchievements(),
                a.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void pointsGoalLockedBelowThreshold() throws Exception {
        p.setPoints(19999);
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.recordRunEnd(d.level());
        assertFalse("19999 points must NOT unlock POINTS_GOAL (proves it reads getPoints, not a constant); got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void timeGoalLockedOnShortRun() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.recordRunEnd(d.level());
        assertFalse("a short run (small getPassedTime) must NOT unlock TIME_GOAL — proves it reads getPassedTime; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("TIME_GOAL"));
    }
    @Test public void onlyReachedGoalUnlocks() throws Exception {
        p.setPoints(20000);
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.recordRunEnd(d.level());
        List<String> u = a.getUnlockedAchievements();
        assertTrue("points goal reached must unlock POINTS_GOAL; got " + u, u.contains("POINTS_GOAL"));
        assertFalse("0 kills must NOT unlock ENEMIES_GOAL; got " + u, u.contains("ENEMIES_GOAL"));
        assertFalse("short run must NOT unlock TIME_GOAL; got " + u, u.contains("TIME_GOAL"));
    }
    @Test public void unlockPersistsAcrossSessions() throws Exception {
        Path s = Files.createTempDirectory("ach").resolve("a.dat");
        p.setPoints(20000);
        ApoMarioStateAchievements a1 = new ApoMarioStateAchievements(s);
        a1.beginRun(); a1.recordRunEnd(d.level()); a1.saveAcrossSessions();
        ApoMarioStateAchievements a2 = new ApoMarioStateAchievements(s);
        assertTrue("a saved POINTS_GOAL must survive into a new session; reloaded " + a2.getUnlockedAchievements(),
                a2.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void noDuplicateOnRepeatedRecord() throws Exception {
        p.setPoints(20000);
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); a.recordRunEnd(d.level());
        a.beginRun(); a.recordRunEnd(d.level());
        assertEquals("POINTS_GOAL must appear exactly once after two recordRunEnd calls; got "
                + a.getUnlockedAchievements(), 1L, count(a.getUnlockedAchievements(), "POINTS_GOAL"));
    }
    @Test public void timeGoalUnlocksAfterLongRun() throws Exception {
        try {
            int cap = 0;
            while (d.level().getPassedTime() < 61000 && cap < 40000) { d.step(1000); cap += 1000; }
            assertTrue("test harness must reach >60000ms elapsed; getPassedTime=" + d.level().getPassedTime(),
                    d.level().getPassedTime() >= 60000);
            ApoMarioStateAchievements a = fresh(); a.beginRun(); a.recordRunEnd(d.level());
            assertTrue("a long run (getPassedTime>=60000) must unlock TIME_GOAL — proves it reads getPassedTime, "
                    + "not getTime; elapsed=" + d.level().getPassedTime() + " got " + a.getUnlockedAchievements(),
                    a.getUnlockedAchievements().contains("TIME_GOAL"));
        } finally {
            d.resetLevel();
        }
    }
}