package apoBot.game;

import org.junit.Test;
import org.junit.BeforeClass;
import static org.junit.Assert.*;
import java.nio.file.Files;
import org.apogames.entity.ApoButton;


public class ApoBotOptionsWiringTest {

    private static IntegrationDriver d;
    private static final int[] MENU_BUTTONS = {1, 2, 3};

    @BeforeClass public static void boot() { d = new IntegrationDriver(); }

    private ApoBotOptions fresh() throws Exception {
        return new ApoBotOptions(Files.createTempFile("opt", ".dat"));
    }

    private Object[][] snapshot() {
        Object[][] s = new Object[MENU_BUTTONS.length][2];
        for (int i = 0; i < MENU_BUTTONS.length; i++) {
            ApoButton b = d.game().getButtons()[MENU_BUTTONS[i]];
            s[i][0] = b;
            s[i][1] = b == null ? null : b.getIBackground();
        }
        return s;
    }
    private int changed(Object[][] before) {
        int n = 0;
        for (int i = 0; i < MENU_BUTTONS.length; i++) {
            ApoButton b = d.game().getButtons()[MENU_BUTTONS[i]];
            Object img = b == null ? null : b.getIBackground();
            if (b != before[i][0] || img != before[i][1]) n++;
        }
        return n;
    }

    @Test public void germanVisiblyChangesLiveMenuButtons() throws Exception {
        ApoBotOptions o = fresh();
        o.setMenuLanguage("en"); o.applyTo(d.game());
        Object[][] before = snapshot();
        o.setMenuLanguage("de"); o.applyTo(d.game());
        assertTrue("applyTo(de) must make the language visible in the LIVE game: the menu buttons "
                + "(tutorial/game/menu) must be rebuilt or re-rendered; none changed",
                changed(before) >= 2);
    }

    @Test public void englishVisiblyRestores() throws Exception {
        ApoBotOptions o = fresh();
        o.setMenuLanguage("de"); o.applyTo(d.game());
        Object[][] german = snapshot();
        o.setMenuLanguage("en"); o.applyTo(d.game());
        assertTrue("switching back to English must visibly re-render the live menu buttons again",
                changed(german) >= 2);
    }
}
