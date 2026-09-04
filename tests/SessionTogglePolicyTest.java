package app.spanishstudy.vot;

public final class SessionTogglePolicyTest {
    private static void expect(boolean expected, boolean actual, String name) {
        if (expected != actual) throw new AssertionError(name + ": expected=" + expected + " actual=" + actual);
    }

    public static void main(String[] args) {
        expect(false, SessionTogglePolicy.nextStateForUserPress(true, false), "user OFF while idle");
        expect(false, SessionTogglePolicy.nextStateForUserPress(true, true), "user OFF while loading");
        expect(true, SessionTogglePolicy.nextStateForUserPress(false, false), "user ON while idle");
        expect(true, SessionTogglePolicy.nextStateForUserPress(false, true), "user ON while loading");
        expect(true, SessionTogglePolicy.nextStateForAutomaticStart(false), "automatic start enables");
        expect(true, SessionTogglePolicy.nextStateForAutomaticStart(true), "automatic start never disables");
        System.out.println("SessionTogglePolicyTest passed");
    }
}
