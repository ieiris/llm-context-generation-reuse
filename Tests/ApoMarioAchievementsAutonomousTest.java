package apoMario.game.panels;

import org.junit.Test;
import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.FixMethodOrder;
import org.junit.runners.MethodSorters;
import static org.junit.Assert.*;
import java.lang.reflect.Field;
import java.util.List;
import apoMario.entity.ApoMarioEnemy;
import apoMario.entity.ApoMarioPlayer;


@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class ApoMarioAchievementsWiringTest {

    private static IntegrationDriver d;
    private ApoMarioPlayer p;

    @BeforeClass public static void boot() { d = new IntegrationDriver(12345L); }
    @Before public void reset() { d.resetLevel(); p = d.player(); p.setPoints(0); }

    private ApoMarioStateAchievements locate() {
        Object hit = scan(d.panel(), 2);
        if (hit == null) hit = scan(d.level(), 1);
        if (hit == null) hit = scanStatics(ApoMarioStateAchievements.class);
        assertNotNull("no live ApoMarioStateAchievements instance reachable from the running game "
                + "(searched panel/level fields and class statics) — feature state is not connected",
                hit);
        return (ApoMarioStateAchievements) hit;
    }
    private Object scan(Object root, int depth) {
        if (root == null || depth < 0) return null;
        for (Class<?> c = root.getClass(); c != null; c = c.getSuperclass()) {
            for (Field f : c.getDeclaredFields()) {
                try {
                    f.setAccessible(true);
                    Object v = f.get(root);
                    if (v instanceof ApoMarioStateAchievements) return v;
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
                if (v instanceof ApoMarioStateAchievements) return v;
            } catch (Exception ignored) { }
        }
        return null;
    }
    private List<String> unlocked() { return locate().getUnlockedAchievements(); }

    private int killEnemies(int n) {
        if (alive() < n) { d.level().makeLevel(12345L, false, true, 300, 1); d.step(2); }
        int killed = 0;
        List<ApoMarioEnemy> enemies = d.level().getEnemies();
        for (int i = 0; i < enemies.size() && killed < n; i++) {
            ApoMarioEnemy e = enemies.get(i);
            if (!e.isBDie()) { e.die(d.level(), 0); killed++; }
        }
        d.step(2);
        return killed;
    }
    private int alive() {
        int c = 0;
        for (ApoMarioEnemy e : d.level().getEnemies()) if (!e.isBDie()) c++;
        return c;
    }

    @Test public void a_nothingUnlocksWithoutReachingAnyGoal() {
        d.step(5);
        d.endRun();
        List<String> u = unlocked();
        assertFalse("an uneventful short run must not unlock POINTS_GOAL; got " + u, u.contains("POINTS_GOAL"));
        assertFalse("an uneventful short run must not unlock ENEMIES_GOAL; got " + u, u.contains("ENEMIES_GOAL"));
        assertFalse("an uneventful short run must not unlock TIME_GOAL; got " + u, u.contains("TIME_GOAL"));
    }

    @Test public void b_twoRealKillsDoNotUnlockEnemiesGoal() {
        assertEquals("test harness must find 2 live enemies in the level", 2, killEnemies(2));
        d.endRun();
        assertFalse("only 2 kills must NOT unlock ENEMIES_GOAL; got " + unlocked(),
                unlocked().contains("ENEMIES_GOAL"));
    }

    @Test public void c_threeRealKillsUnlockEnemiesGoal() {
        assertEquals("test harness must find 3 live enemies in the level", 3, killEnemies(3));
        d.endRun();
        assertTrue("3 real enemy.die() kills in one run must unlock ENEMIES_GOAL via the game's own "
                + "wiring (no test call); got " + unlocked(), unlocked().contains("ENEMIES_GOAL"));
    }

    @Test public void d_realPointsUnlockPointsGoalOnRunEnd() {
        p.setPoints(20000);
        d.endRun();
        assertTrue("20000 real points at run end must unlock POINTS_GOAL via the game's own wiring; got "
                + unlocked(), unlocked().contains("POINTS_GOAL"));
    }

    @Test public void e_realSixtySecondRunUnlocksTimeGoal() {
        int cap = 0;
        while (d.level().getPassedTime() < 61000 && cap < 40000) { d.step(1000); cap += 1000; }
        assertTrue("test harness must reach >60000ms elapsed; getPassedTime=" + d.level().getPassedTime(),
                d.level().getPassedTime() >= 60000);
        d.endRun();
        assertTrue("surviving 60s in a real run must unlock TIME_GOAL via the game's own wiring "
                + "(no test call); got " + unlocked(), unlocked().contains("TIME_GOAL"));
    }
}
