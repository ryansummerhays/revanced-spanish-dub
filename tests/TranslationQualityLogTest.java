package app.spanishstudy.vot;

public final class TranslationQualityLogTest {
    private static void require(boolean ok, String name) {
        if (!ok) throw new AssertionError(name);
    }

    public static void main(String[] args) {
        TranslationQualityLog.clear();
        TranslationQualityLog.beginVideo("video-a");
        TranslationQualityLog.record("openrouter", "mistralai/mistral-nemo", 7, 1200, 4300,
                "Take the high ground.\nNow!", "Toma el terreno elevado. ¡Ahora!");
        String dump = TranslationQualityLog.dump();
        require(dump.contains("idx=7"), "index recorded");
        require(dump.contains("t=1200-4300ms"), "timing recorded");
        require(dump.contains("provider=openrouter"), "provider recorded");
        require(dump.contains("model=mistralai/mistral-nemo"), "model recorded");
        require(dump.contains("EN: Take the high ground. Now!"), "source normalized");
        require(dump.contains("ES: Toma el terreno elevado. ¡Ahora!"), "translation recorded");

        TranslationQualityLog.record("google", "-", 8, 5000, 7000, "Missing test", null);
        require(TranslationQualityLog.dump().contains("ES: <missing>"), "missing translation explicit");

        for (int i = 0; i < 130; i++) {
            TranslationQualityLog.record("openrouter", "model", i, i, i + 1, "source " + i, "target " + i);
        }
        require(TranslationQualityLog.size() == 120, "ring buffer bounded");
        require(!TranslationQualityLog.dump().contains("source 0 ||"), "oldest rows evicted");

        TranslationQualityLog.beginVideo("video-b");
        require(TranslationQualityLog.size() == 0, "new video clears prior quality trace");
        System.out.println("TranslationQualityLogTest passed");
    }
}
