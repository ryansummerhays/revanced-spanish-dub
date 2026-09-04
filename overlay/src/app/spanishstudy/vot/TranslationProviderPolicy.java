package app.spanishstudy.vot;

/**
 * Pure policy for the Spanish Dub Study text-provider path.
 *
 * The normal Morphe provider setting remains authoritative. OpenRouter is therefore used only when
 * the user selected OpenRouter. If an OpenRouter batch fails for an ordinary network/provider
 * reason, the rest of that translation session can fail forward to Google without changing the
 * saved provider setting. Abort/seek cuts are transport control, not provider failures.
 */
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
