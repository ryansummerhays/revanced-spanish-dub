package app.spanishstudy.vot;

/** Pure policy separating explicit user intent from automatic startup/lifecycle behavior. */
public final class SessionTogglePolicy {
    private SessionTogglePolicy() {}

    /** A real user button press always flips the session, regardless of loading state. */
    public static boolean nextStateForUserPress(boolean currentlyEnabled, boolean loading) {
        return !currentlyEnabled;
    }

    /** Automatic startup is idempotent: it may enable, but must never disable an active session. */
    public static boolean nextStateForAutomaticStart(boolean currentlyEnabled) {
        return true;
    }
}
