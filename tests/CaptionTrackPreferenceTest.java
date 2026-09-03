package app.spanishstudy.vot;

public final class CaptionTrackPreferenceTest {
    public static void main(String[] args) {
        englishBeatsSpanishTarget();
        regionalEnglishStillCounts();
        nonGeminiWinsWithinSameLanguageTier();
        targetIsFallbackWhenEnglishMissing();
        normalizesLanguageTags();
        System.out.println("caption track preference: OK");
    }

    private static void englishBeatsSpanishTarget() {
        int english = CaptionTrackPreference.rank("en", true, "es-US");
        int spanish = CaptionTrackPreference.rank("es-US", true, "es-US");
        require(english < spanish,
                "Spanish dub target must never outrank English study/source captions");
    }

    private static void regionalEnglishStillCounts() {
        require(CaptionTrackPreference.isEnglish("en-US"), "en-US should be English");
        require(CaptionTrackPreference.isEnglish("en_GB"), "en_GB should be English");
        require(CaptionTrackPreference.rank("en-GB", true, "es") == 0,
                "regional English should receive top source rank");
    }

    private static void nonGeminiWinsWithinSameLanguageTier() {
        require(CaptionTrackPreference.rank("en", true, "es")
                        < CaptionTrackPreference.rank("en", false, "es"),
                "ordinary English track should beat Gemini variant");
    }

    private static void targetIsFallbackWhenEnglishMissing() {
        int target = CaptionTrackPreference.rank("es", true, "es-US");
        int unrelated = CaptionTrackPreference.rank("fr", true, "es-US");
        require(target < unrelated,
                "target-language captions should remain a fallback when English is absent");
    }

    private static void normalizesLanguageTags() {
        require(CaptionTrackPreference.base(" EN_us ").equals("en"),
                "language normalization failed");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
