import org.junit.Test;
import static org.junit.Assert.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ApoMarioHighscoreTest {

    private ApoMarioHighscore fresh() throws Exception {
        return new ApoMarioHighscore(Files.createTempDirectory("hs").resolve("highscores.dat"));
    }

    @Test public void emptyBoardInitially() throws Exception {
        ApoMarioHighscore h = fresh();
        assertTrue("fresh board must have no names; got " + h.getPlayersNames(), h.getPlayersNames().isEmpty());
        assertTrue("fresh board must have no scores; got " + h.getPlayersScores(), h.getPlayersScores().isEmpty());
        assertTrue("fresh board must have no survival times; got " + h.getSurvivalTimes(), h.getSurvivalTimes().isEmpty());
    }

    @Test public void saveAddsEntry() throws Exception {
        ApoMarioHighscore h = fresh();
        h.storeRun(1000, 42, "Alice");
        assertEquals("storeRun must add exactly one entry; names=" + h.getPlayersNames(), 1, h.getPlayersNames().size());
        int i = h.getPlayersNames().indexOf("Alice");
        assertTrue("stored player 'Alice' must be retrievable; names=" + h.getPlayersNames(), i >= 0);
        assertEquals("score for 'Alice' must equal the value passed to storeRun; scores=" + h.getPlayersScores(),
                Integer.valueOf(1000), h.getPlayersScores().get(i));
        assertEquals("survival time for 'Alice' must equal the value passed to storeRun (check score/time not swapped); times="
                + h.getSurvivalTimes(), Integer.valueOf(42), h.getSurvivalTimes().get(i));
    }

    @Test public void parallelListsAligned() throws Exception {
        ApoMarioHighscore h = fresh();
        h.storeRun(500, 30, "Bob");
        h.storeRun(900, 60, "Carol");
        int n = h.getPlayersNames().size();
        assertEquals("names and scores must be the same length; names=" + h.getPlayersNames() + " scores="
                + h.getPlayersScores(), n, h.getPlayersScores().size());
        assertEquals("names and survival-times must be the same length; names=" + h.getPlayersNames() + " times="
                + h.getSurvivalTimes(), n, h.getSurvivalTimes().size());
        int i = h.getPlayersNames().indexOf("Carol");
        assertEquals("score must stay index-aligned with 'Carol'; scores=" + h.getPlayersScores(),
                Integer.valueOf(900), h.getPlayersScores().get(i));
        assertEquals("survival time must stay index-aligned with 'Carol'; times=" + h.getSurvivalTimes(),
                Integer.valueOf(60), h.getSurvivalTimes().get(i));
    }

    @Test public void boardSortedDescendingByPoints() throws Exception {
        ApoMarioHighscore h = fresh();
        h.storeRun(300, 10, "C"); h.storeRun(900, 40, "A"); h.storeRun(600, 25, "B");
        List<Integer> pts = h.getPlayersScores();
        for (int i = 1; i < pts.size(); i++)
            assertTrue("scores must be in non-increasing order; scores=" + pts, pts.get(i - 1) >= pts.get(i));
        assertEquals("highest score (900, 'A') must be first; names=" + h.getPlayersNames(),
                "A", h.getPlayersNames().get(0));
    }

    @Test public void entriesPersistAcrossSessions() throws Exception {
        Path s = Files.createTempDirectory("hs").resolve("highscores.dat");
        ApoMarioHighscore h = new ApoMarioHighscore(s);
        h.storeRun(1500, 70, "Eve"); h.persistAcrossRuns();
        ApoMarioHighscore r = new ApoMarioHighscore(s);
        assertEquals("a persisted run must survive into a new session; reloaded names=" + r.getPlayersNames(),
                1, r.getPlayersNames().size());
        assertEquals("persisted player name must be restored; reloaded names=" + r.getPlayersNames(),
                "Eve", r.getPlayersNames().get(0));
        assertEquals("persisted score must be restored; reloaded scores=" + r.getPlayersScores(),
                Integer.valueOf(1500), r.getPlayersScores().get(0));
    }

    @Test public void emptyPersistRobust() throws Exception {
        Path s = Files.createTempDirectory("hs").resolve("highscores.dat");
        new ApoMarioHighscore(s);
        List<String> u = new ApoMarioHighscore(s).getPlayersNames();
        assertTrue("constructing on an empty/never-written store must yield an empty board (no crash); got " + u,
                u.isEmpty());
    }

    @Test public void rankingPreservedAfterReload() throws Exception {
        Path s = Files.createTempDirectory("hs").resolve("highscores.dat");
        ApoMarioHighscore h = new ApoMarioHighscore(s);
        h.storeRun(400, 20, "p400"); h.storeRun(1200, 55, "p1200"); h.storeRun(800, 35, "p800"); h.persistAcrossRuns();
        ApoMarioHighscore r = new ApoMarioHighscore(s);
        assertEquals("after reload, highest score (1200, 'p1200') must be first; reloaded names=" + r.getPlayersNames(),
                "p1200", r.getPlayersNames().get(0));
        List<Integer> pts = r.getPlayersScores();
        for (int i = 1; i < pts.size(); i++)
            assertTrue("after reload, scores must still be non-increasing; reloaded scores=" + pts,
                    pts.get(i - 1) >= pts.get(i));
    }
}