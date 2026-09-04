package app.spanishstudy.vot;

public final class DubLanguageGuardV217Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(!DubLanguageGuard.isSafeTranslation(
                        "What do you think about that?",
                        "What do you think about that?", "es"),
                "unchanged English sentence must be rejected");

        check(!DubLanguageGuard.isSafeTranslation(
                        "I really don't know what they were doing there.",
                        "I really do not know what they were doing there.", "es"),
                "slightly paraphrased English output must be rejected");

        check(DubLanguageGuard.isSafeTranslation(
                        "What do you think about that?",
                        "¿Qué piensas de eso?", "es"),
                "normal Spanish translation must pass");

        check(DubLanguageGuard.isSafeTranslation(
                        "New York City",
                        "New York City", "es"),
                "proper names must not be blocked merely for staying unchanged");

        check(DubLanguageGuard.isSafeTranslation(
                        "Okay.",
                        "Okay.", "es"),
                "short ambiguous interjections should pass the conservative guard");

        check(DubLanguageGuard.isSafeTranslation(
                        "What do you think about that?",
                        "What do you think about that?", "fr"),
                "guard must not alter non-Spanish targets");
    }
}