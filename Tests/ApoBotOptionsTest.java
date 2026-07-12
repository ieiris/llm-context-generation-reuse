import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.nio.file.Path;
import org.junit.Test;

public class ApoBotOptionsTest {

    private static final String GERMAN = "de";
    private static final String ENGLISH = "en";

    private static Path freshStore() throws Exception {
        File store = File.createTempFile("apoBotOptions", ".dat");
        store.delete();
        store.deleteOnExit();
        return store.toPath();
    }

    @Test
    public void defaultsToEnglishAndSoundOn() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        assertEquals("default menu language must be English ('en'); got '" + options.getMenuLanguage() + "'",
                ENGLISH, options.getMenuLanguage());
        assertTrue("sound must be ON by default; isSoundTriggered() returned " + options.isSoundTriggered(),
                options.isSoundTriggered());
    }

    @Test
    public void selectingGermanActivatesGerman() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        options.setMenuLanguage(GERMAN);
        assertEquals("after setMenuLanguage('de'), getMenuLanguage() must return 'de'; got '"
                + options.getMenuLanguage() + "'", GERMAN, options.getMenuLanguage());
    }

    @Test
    public void selectingEnglishActivatesEnglish() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        options.setMenuLanguage(GERMAN); // because english is default
        options.setMenuLanguage(ENGLISH);
        assertEquals("after setting 'de' then 'en', getMenuLanguage() must return 'en'; got '"
                + options.getMenuLanguage() + "'", ENGLISH, options.getMenuLanguage());
    }

    @Test
    public void unsupportedLanguageIsNeverActivated() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        options.setMenuLanguage(GERMAN);
        try {
            options.setMenuLanguage("fr");          // silently ignoring OR rejecting are both valid
        } catch (RuntimeException expectedAndAllowed) { }
        assertEquals("an unsupported language ('fr') must never become the active language; expected 'de' got '"
                + options.getMenuLanguage() + "'", GERMAN, options.getMenuLanguage());
    }

    @Test
    public void soundCanBeTurnedOff() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        options.setSound(false);
        assertFalse("after setSound(false), isSoundTriggered() must be false; got " + options.isSoundTriggered(),
                options.isSoundTriggered());
    }

    @Test
    public void soundCanBeTurnedOn() throws Exception {
        ApoBotOptions options = new ApoBotOptions(freshStore());
        options.setSound(false); // because on is default
        options.setSound(true);
        assertTrue("after setSound(false) then setSound(true), isSoundTriggered() must be true; got "
                + options.isSoundTriggered(), options.isSoundTriggered());
    }

    @Test
    public void preferencesSurviveAReloadInANewSession() throws Exception {
        Path store = freshStore();

        ApoBotOptions session1 = new ApoBotOptions(store);
        session1.setMenuLanguage(GERMAN);
        session1.setSound(false);
        session1.persistAcrossSessions();

        ApoBotOptions session2 = new ApoBotOptions(store);
        assertEquals("language set+persisted in session 1 must be restored in session 2 ('de'); got '"
                + session2.getMenuLanguage() + "'", GERMAN, session2.getMenuLanguage());
        assertFalse("sound set OFF+persisted in session 1 must be restored OFF in session 2; got "
                + session2.isSoundTriggered(), session2.isSoundTriggered());
    }

    @Test
    public void preferencesAreOnlyRestoredAfterPersist() throws Exception {
        Path store = freshStore();

        ApoBotOptions session1 = new ApoBotOptions(store);
        session1.setMenuLanguage(GERMAN);
        session1.setSound(false);

        ApoBotOptions session2 = new ApoBotOptions(store);
        assertEquals("without persistAcrossSessions(), language must stay at default 'en' in a new session; got '"
                + session2.getMenuLanguage() + "'", ENGLISH, session2.getMenuLanguage());
        assertTrue("without persistAcrossSessions(), sound must stay at default ON in a new session; got "
                + session2.isSoundTriggered(), session2.isSoundTriggered());
    }
}