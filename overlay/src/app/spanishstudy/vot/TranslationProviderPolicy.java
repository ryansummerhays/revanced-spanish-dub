package app.spanishstudy.vot;

/** Pure provider policy for Spanish Dub Study translation routing. */
public final class TranslationProviderPolicy {
    public static final String GOOGLE = "google";
    public static final String OPENROUTER = "openrouter";

    private TranslationProviderPolicy() {}

    public static boolean shouldUseOpenRouter(String selectedService, boolean fallbackLatched) {
        return OPENROUTER.equals(selectedService) && !fallbackLatched;
    }

    public static boolean shouldFallbackToGoogle(String selectedService,
                                                 boolean aborting,
                                                 boolean reprioritizing) {
        return OPENROUTER.equals(selectedService) && !aborting && !reprioritizing;
    }

    public static String effectiveService(String selectedService, boolean fallbackLatched) {
        return shouldUseOpenRouter(selectedService, fallbackLatched) ? OPENROUTER : selectedService;
    }
}
