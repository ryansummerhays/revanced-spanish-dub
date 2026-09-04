package app.spanishstudy.vot;

public final class TranslationProvenanceLogTest {
    public static void main(String[] args) {
        TranslationProvenanceLog.beginVideo("a");
        TranslationProvenanceLog.markReady("a", 4, "openrouter", "m", "stream", "hola");
        String first = TranslationProvenanceLog.describe(4, "hola");
        check(first.contains("provider=openrouter"), "provider");
        check(first.contains("path=stream"), "stream path");
        TranslationProvenanceLog.markReady("a", 4, "google", "-", "final", "hola");
        check(TranslationProvenanceLog.describe(4, "hola").contains("provider=openrouter"), "first-ready wins");
        TranslationProvenanceLog.beginVideo("b");
        check(TranslationProvenanceLog.size() == 0, "reset");
        System.out.println("TranslationProvenanceLogTest OK");
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }
}
