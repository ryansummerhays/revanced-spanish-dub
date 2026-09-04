#!/usr/bin/env python3
"""Final v2.14 layer: native provider toggling, OpenRouter->Google fail-forward, conservative cue diagnostics."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v214_openrouter_final.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"

    rep(translator,
'''import app.spanishstudy.vot.StartupTranslationPlanner;''',
'''import app.spanishstudy.vot.StartupTranslationPlanner;
import app.spanishstudy.vot.TranslationProviderPolicy;''',
        "import tested translation provider policy")

    rep(translator,
'''        // v2.10 stable baseline: only Google translates Spanish Dub Study transcripts.
        String service = TRANSLATION_SERVICE_GOOGLE;
        final boolean isMyMemory = false;
        final boolean isOpenRouter = false;''',
'''        // v2.14 final: Morphe's normal provider setting is authoritative again.
        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);''',
        "restore normal Morphe provider authority")

    rep(translator,
'''    private static volatile boolean reportNextTranslationError;''',
'''    private static volatile boolean reportNextTranslationError;
    // Ordinary OpenRouter failure latches Google for the remainder of this translate() session.
    // The saved Morphe provider setting is never rewritten, so the user's cost/quality choice stays intact.
    private static volatile boolean openRouterFallbackToGoogle;''',
        "add OpenRouter fallback latch")

    rep(translator,
'''        abortTranslation = false;
        reprioritize = false;''',
'''        abortTranslation = false;
        reprioritize = false;
        openRouterFallbackToGoogle = false;''',
        "reset provider fallback for each translation session")

    rep(translator,
'''    /** Aborts any running translation and disconnects the in-flight HTTP request if any. */
    static void requestAbort() {''',
'''    public static String selectedServiceForDiagnostics() {
        return Settings.VOT_TRANSLATION_SERVICE.get();
    }

    public static String effectiveServiceForDiagnostics() {
        String selected = Settings.VOT_TRANSLATION_SERVICE.get();
        return TranslationProviderPolicy.effectiveService(selected, openRouterFallbackToGoogle);
    }

    /** Aborts any running translation and disconnects the in-flight HTTP request if any. */
    static void requestAbort() {''',
        "expose selected/effective provider diagnostics")

    rep(translator,
'''        if (service.equals(TRANSLATION_SERVICE_OPENROUTER)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        return translateBatchGoogle(videoId, segments, targetLang);''',
'''        if (TranslationProviderPolicy.shouldUseOpenRouter(service, openRouterFallbackToGoogle)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        // A failed OpenRouter session stays on Google until this translate() call finishes.
        return translateBatchGoogle(videoId, segments, targetLang);''',
        "route latched OpenRouter fallback through Google")

    rep(translator,
'''            if (abortTranslation || reprioritize) {
                Logger.printDebug(() -> "Translation aborted: " + ex.getMessage());
                return null;
            }
            String msg = ex.getMessage();''',
'''            if (abortTranslation || reprioritize) {
                Logger.printDebug(() -> "Translation aborted: " + ex.getMessage());
                return null;
            }
            final String selectedService = Settings.VOT_TRANSLATION_SERVICE.get();
            if (TranslationProviderPolicy.shouldFallbackToGoogle(
                    selectedService, abortTranslation, reprioritize)) {
                openRouterFallbackToGoogle = true;
                SpanishStudyDiagnostics.record("PROVIDER", "openrouter failed; google fallback events="
                        + batch.size() + " cause=" + ex.getClass().getSimpleName());
                try {
                    return translateBatchGoogle(videoId, batch, targetLang);
                } catch (Exception googleEx) {
                    SpanishStudyDiagnostics.record("PROVIDER", "google fallback failed events="
                            + batch.size() + " cause=" + googleEx.getClass().getSimpleName());
                    ex.addSuppressed(googleEx);
                }
            }
            String msg = ex.getMessage();''',
        "fail ordinary OpenRouter batch errors forward to Google")

    rep(translator,
'''                if (completed < batchDone.size() && batchDelay > 0) {
                    try {
                        //noinspection BusyWait
                        Thread.sleep(batchDelay);''',
'''                final int effectiveBatchDelay = openRouterFallbackToGoogle
                        ? GOOGLE_INTER_BATCH_DELAY_MS : batchDelay;
                if (completed < batchDone.size() && effectiveBatchDelay > 0) {
                    try {
                        //noinspection BusyWait
                        Thread.sleep(effectiveBatchDelay);''',
        "use Google pacing after OpenRouter fallback")

    rep(controller,
'''import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;''',
'''import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptTranslator;''',
        "import translator diagnostics into study controller")

    rep(controller,
'''        report.append("translationMode=google-only-stable\\n");''',
'''        report.append("translationMode=morphe-native-provider\\n");
        report.append("providerAuthority=normal-morphe-setting\\n");
        report.append("translationFallback=google-on-openrouter-failure\\n");
        report.append("selectedProvider=").append(TranscriptTranslator.selectedServiceForDiagnostics()).append('\\n');
        report.append("effectiveProvider=").append(TranscriptTranslator.effectiveServiceForDiagnostics()).append('\\n');''',
        "diagnose provider toggle and effective fallback")

    rep(controller,
'''        report.append("captionSpeakerMarkers=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("captionNamedSpeakers=").append(CaptionNamedSpeakerStore.namedSpeakerCount()).append('\\n');
        report.append("speakerBoundaryMode=caption-markers-provisional-hard-boundary\\n");
        report.append("speakerIdentityMode=caption-names-then-local-audio-clustering\\n");''',
'''        report.append("captionCueMarkers=").append(CaptionSpeakerTurnStore.markerCount()).append('\\n');
        report.append("captionSpeakerTurns=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("captionNamedSpeakers=").append(CaptionNamedSpeakerStore.namedSpeakerCount()).append('\\n');
        report.append("speakerBoundaryMode=explicit-labelled-caption-turns-only\\n");
        report.append("speakerIdentityMode=caption-names-then-local-audio-clustering\\n");''',
        "diagnose cue markers separately from trusted speaker turns")

    print("v2.14 final OpenRouter/provider-toggle integration complete")


if __name__ == "__main__":
    main()
