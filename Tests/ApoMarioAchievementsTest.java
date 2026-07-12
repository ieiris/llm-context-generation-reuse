import org.junit.Test;
import static org.junit.Assert.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ApoMarioAchievementsTest {

    private static final int  POINTS_GOAL  = 20000;
    private static final int  ENEMIES_GOAL = 3;
    private static final long TIME_GOAL_MS = 60000L;
    private static final int  TICK         = 16;

    private ApoMarioStateAchievements fresh() throws Exception {
        return new ApoMarioStateAchievements(Files.createTempDirectory("ach").resolve("achievements.dat"));
    }
    private long count(List<String> l, String id) {
        long c = 0; for (String s : l) if (s.equals(id)) c++; return c;
    }

    @Test public void pointsUnlocksAtGoal() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.addPoints(POINTS_GOAL);
        assertTrue("reaching " + POINTS_GOAL + " points in a run must unlock 'POINTS_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void killsUnlockAtGoal() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun();
        for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        assertTrue("killing " + ENEMIES_GOAL + " enemies in a run must unlock 'ENEMIES_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("ENEMIES_GOAL"));
    }
    @Test public void timerUnlocksPastGoal() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.addTimeSurvived(TIME_GOAL_MS + 2L * TICK);
        assertTrue("surviving more than " + TIME_GOAL_MS + "ms must unlock 'TIME_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("TIME_GOAL"));
    }

    @Test public void pointsBelowGoalLocked() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.addPoints(POINTS_GOAL - 1);
        assertFalse("only " + (POINTS_GOAL - 1) + " points must NOT unlock 'POINTS_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void killsBelowGoalLocked() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun();
        for (int i = 0; i < ENEMIES_GOAL - 1; i++) a.addEnemyKilled();
        assertFalse("only " + (ENEMIES_GOAL - 1) + " kills must NOT unlock 'ENEMIES_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("ENEMIES_GOAL"));
    }
    @Test public void timeBelowGoalLocked() throws Exception {
        ApoMarioStateAchievements a = fresh(); a.beginRun(); a.addTimeSurvived(TIME_GOAL_MS - 2L * TICK);
        assertFalse("only " + (TIME_GOAL_MS - 2L * TICK) + "ms must NOT unlock 'TIME_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("TIME_GOAL"));
    }

    @Test public void pointsDoNotCombineAcrossRuns() throws Exception {
        ApoMarioStateAchievements a = fresh();
        int half = POINTS_GOAL / 2, rest = POINTS_GOAL - half;
        a.beginRun(); a.addPoints(rest);
        a.beginRun(); a.addPoints(half);
        assertFalse("points must reset on beginRun() - " + rest + " then " + half
                        + " in separate runs must NOT unlock 'POINTS_GOAL'; got " + a.getUnlockedAchievements(),
                a.getUnlockedAchievements().contains("POINTS_GOAL"));
    }
    @Test public void killsDoNotCarryAcrossRuns() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); for (int i = 0; i < ENEMIES_GOAL - 1; i++) a.addEnemyKilled();
        a.beginRun(); a.addEnemyKilled();
        assertFalse("kills must reset on beginRun() - " + (ENEMIES_GOAL - 1)
                        + " then 1 in separate runs must NOT unlock 'ENEMIES_GOAL'; got " + a.getUnlockedAchievements(),
                a.getUnlockedAchievements().contains("ENEMIES_GOAL"));
    }
    @Test public void timerResetsEachRun() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); a.addTimeSurvived(TIME_GOAL_MS - 2L * TICK);
        a.beginRun(); a.addTimeSurvived(2L * TICK);
        assertFalse("survival time must reset on beginRun() - two sub-threshold runs must NOT unlock 'TIME_GOAL'; got "
                + a.getUnlockedAchievements(), a.getUnlockedAchievements().contains("TIME_GOAL"));
    }

    @Test public void lockedStaysLockedAfterRestart() throws Exception {
        Path s = Files.createTempDirectory("ach").resolve("achievements.dat");
        new ApoMarioStateAchievements(s).saveAcrossSessions();
        List<String> u = new ApoMarioStateAchievements(s).getUnlockedAchievements();
        assertTrue("saving with nothing unlocked, then reloading, must give an EMPTY list; got " + u, u.isEmpty());
    }
    @Test public void multipleAchievementsPersist() throws Exception {
        Path s = Files.createTempDirectory("ach").resolve("achievements.dat");
        ApoMarioStateAchievements a = new ApoMarioStateAchievements(s);
        a.beginRun(); a.addPoints(POINTS_GOAL);
        for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        a.addTimeSurvived(TIME_GOAL_MS + 2L * TICK); a.saveAcrossSessions();
        List<String> u = new ApoMarioStateAchievements(s).getUnlockedAchievements();
        assertTrue("all three milestones, once saved, must survive into a new session; reloaded " + u,
                u.contains("POINTS_GOAL") && u.contains("ENEMIES_GOAL") && u.contains("TIME_GOAL"));
    }

    @Test public void reHitSameRunNoDuplicate() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); a.addPoints(POINTS_GOAL); a.addPoints(500); a.addTimeSurvived(2L * TICK);
        assertEquals("'POINTS_GOAL' must appear exactly once after re-crossing the threshold in one run; got "
                + a.getUnlockedAchievements(), 1L, count(a.getUnlockedAchievements(), "POINTS_GOAL"));
    }
    @Test public void reUnlockLaterRunNoDuplicate() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        a.beginRun(); for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        assertEquals("'ENEMIES_GOAL' must appear exactly once even when re-earned in a later run; got "
                + a.getUnlockedAchievements(), 1L, count(a.getUnlockedAchievements(), "ENEMIES_GOAL"));
    }

    @Test public void multipleUnlockInOneRun() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); a.addPoints(POINTS_GOAL);
        for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        List<String> u = a.getUnlockedAchievements();
        assertTrue("one run hitting points AND kills must unlock both 'POINTS_GOAL' and 'ENEMIES_GOAL'; got " + u,
                u.contains("POINTS_GOAL") && u.contains("ENEMIES_GOAL"));
    }
    @Test public void unlockingOneDoesNotAffectOthers() throws Exception {
        ApoMarioStateAchievements a = fresh();
        a.beginRun(); for (int i = 0; i < ENEMIES_GOAL; i++) a.addEnemyKilled();
        List<String> u = a.getUnlockedAchievements();
        assertTrue("reaching only the kill goal must unlock 'ENEMIES_GOAL'; got " + u, u.contains("ENEMIES_GOAL"));
        assertFalse("reaching only the kill goal must NOT unlock 'POINTS_GOAL'; got " + u, u.contains("POINTS_GOAL"));
        assertFalse("reaching only the kill goal must NOT unlock 'TIME_GOAL'; got " + u, u.contains("TIME_GOAL"));
    }

    @Test public void startsEmpty() throws Exception {
        List<String> u = fresh().getUnlockedAchievements();
        assertTrue("a fresh instance must have no unlocked achievements; got " + u, u.isEmpty());
    }
}