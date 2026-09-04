#!/usr/bin/env python3
"""v2.14.1: make OpenRouter dispatch observable and fail forward on silent/null results."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2141_openrouter_runtime.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    translator = pkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"

    text = translator.read_text(encoding="utf-8")

    # Keep provider/network failures distinct from explicit session/video aborts. Morphe uses the
    # same abortTranslation bit for some fatal provider responses, so that bit alone is not enough
    # to decide whether a Google fail-forward would be stale.
    field_anchor = '''    private static volatile boolean openRouterFallbackToGoogle;'''
    if text.count(field_anchor) != 1:
        raise RuntimeError("OpenRouter fallback field anchor missing")
    text = text.replace(field_anchor, field_anchor + '''
    // True only when requestAbort() was called because the current translation is no longer wanted.
    // Provider failures may also set abortTranslation, but must not set this flag.
    private static volatile boolean externalAbortRequested;''', 1)

    reset_anchor = '''        openRouterFallbackToGoogle = false;'''
    if text.count(reset_anchor) != 1:
        raise RuntimeError(f"fallback reset anchor count={text.count(reset_anchor)}")
    text = text.replace(reset_anchor, reset_anchor + '''
        externalAbortRequested = false;''', 1)

    abort_anchor = '''    static void requestAbort() {
        abortTranslation = true;'''
    if text.count(abort_anchor) != 1:
        raise RuntimeError(f"requestAbort anchor count={text.count(abort_anchor)}")
    text = text.replace(abort_anchor, '''    static void requestAbort() {
        externalAbortRequested = true;
        abortTranslation = true;''', 1)

    signature = '''    @Nullable\n    private static List<String> translateBatchSafe(String videoId,'''
    if text.count(signature) != 1:
        raise RuntimeError(f"translateBatchSafe signature count={text.count(signature)}")

    # Keep Morphe's existing error/reporting behavior intact, but wrap it so a swallowed/null
    # OpenRouter result cannot leave the entire transcript in English indefinitely.
    text = text.replace(signature,
'''    @Nullable
    private static List<String> translateBatchSafeOriginal(String videoId,''', 1)

    original_sig = '''    @Nullable
    private static List<String> translateBatchSafeOriginal(String videoId,'''
    at = text.index(original_sig)
    wrapper = '''    @Nullable
    private static List<String> translateBatchSafe(String videoId,
                                                   List<TranscriptSegment> batch, String targetLang,
                                                   @Nullable Consumer<List<String>> onLineStreamed) {
        final String selected = Settings.VOT_TRANSLATION_SERVICE.get();
        final String effectiveBefore = TranslationProviderPolicy.effectiveService(
                selected, openRouterFallbackToGoogle);
        SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "request selected=" + selected
                + " effective=" + effectiveBefore + " events=" + batch.size()
                + (selected.equals(TRANSLATION_SERVICE_OPENROUTER)
                   ? " model=" + Settings.VOT_OPENROUTER_MODEL.get().trim() : ""));

        List<String> translated = translateBatchSafeOriginal(
                videoId, batch, targetLang, onLineStreamed);
        if (translated != null && !translated.isEmpty()) {
            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "result provider="
                    + TranslationProviderPolicy.effectiveService(selected, openRouterFallbackToGoogle)
                    + " outputs=" + translated.size());
            return translated;
        }

        SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "empty-result selected=" + selected
                + " abort=" + abortTranslation + " externalAbort=" + externalAbortRequested
                + " reprioritize=" + reprioritize);

        // Some OpenRouter/Morphe failure paths return null instead of propagating an exception.
        // Fail those forward to Google unless the request was explicitly cancelled because the
        // session/video is no longer current or a seek is actively reprioritizing the stream.
        if (selected.equals(TRANSLATION_SERVICE_OPENROUTER)
                && !externalAbortRequested && !reprioritize) {
            openRouterFallbackToGoogle = true;
            try {
                List<String> fallback = translateBatchGoogle(videoId, batch, targetLang);
                if (fallback != null && !fallback.isEmpty()) {
                    // A provider-fatal OpenRouter error may have set abortTranslation. The current
                    // session is still wanted, so clear that generic provider-abort after successful
                    // Google recovery. requestAbort() is protected by externalAbortRequested above.
                    abortTranslation = false;
                }
                SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "null-result google fallback outputs="
                        + (fallback == null ? -1 : fallback.size()));
                return fallback;
            } catch (Exception fallbackEx) {
                String msg = fallbackEx.getMessage();
                if (msg == null) msg = "";
                msg = msg.replace('\\n', ' ').replace('\\r', ' ');
                if (msg.length() > 180) msg = msg.substring(0, 180);
                final String detail = msg;
                SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "google fallback exception="
                        + fallbackEx.getClass().getSimpleName() + " msg=" + detail);
            }
        }
        return translated;
    }

'''
    text = text[:at] + wrapper + text[at:]

    # Record the actual exception swallowed by Morphe's safe wrapper. Never record the API key.
    catch_anchor = '''        } catch (Exception ex) {
            if (abortTranslation || reprioritize) {'''
    method_start = text.index(original_sig)
    method_end = text.find("\n    /**", method_start)
    if method_end < 0:
        raise RuntimeError("could not bound translateBatchSafeOriginal")
    method = text[method_start:method_end]
    if method.count(catch_anchor) != 1:
        raise RuntimeError(f"safe-wrapper catch anchor count={method.count(catch_anchor)}")
    catch_replacement = '''        } catch (Exception ex) {
            String runtimeMsg = ex.getMessage();
            if (runtimeMsg == null) runtimeMsg = "";
            runtimeMsg = runtimeMsg.replace('\\n', ' ').replace('\\r', ' ');
            if (runtimeMsg.length() > 180) runtimeMsg = runtimeMsg.substring(0, 180);
            final String runtimeDetail = runtimeMsg;
            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "exception selected="
                    + Settings.VOT_TRANSLATION_SERVICE.get() + " type="
                    + ex.getClass().getSimpleName() + " msg=" + runtimeDetail);
            if (abortTranslation || reprioritize) {'''
    method = method.replace(catch_anchor, catch_replacement, 1)
    text = text[:method_start] + method + text[method_end:]

    # Diagnostic helpers expose only whether a key exists, never the secret itself.
    diagnostics_anchor = '''    public static String effectiveServiceForDiagnostics() {
        String selected = Settings.VOT_TRANSLATION_SERVICE.get();
        return TranslationProviderPolicy.effectiveService(selected, openRouterFallbackToGoogle);
    }
'''
    if text.count(diagnostics_anchor) != 1:
        raise RuntimeError("effective diagnostics helper anchor missing")
    text = text.replace(diagnostics_anchor, diagnostics_anchor + '''
    public static boolean openRouterConfiguredForDiagnostics() {
        return !Settings.VOT_OPENROUTER_API_KEY.get().trim().isEmpty();
    }

    public static String openRouterModelForDiagnostics() {
        return Settings.VOT_OPENROUTER_MODEL.get().trim();
    }
''', 1)
    translator.write_text(text, encoding="utf-8")

    ctext = controller.read_text(encoding="utf-8")
    c_anchor = '''        report.append("effectiveProvider=").append(TranscriptTranslator.effectiveServiceForDiagnostics()).append('\\n');'''
    if ctext.count(c_anchor) != 1:
        raise RuntimeError("controller effective provider anchor missing")
    ctext = ctext.replace(c_anchor, c_anchor + '''
        report.append("openRouterConfigured=").append(TranscriptTranslator.openRouterConfiguredForDiagnostics()).append('\\n');
        report.append("openRouterModel=").append(TranscriptTranslator.openRouterModelForDiagnostics()).append('\\n');
        report.append("providerRuntimeTelemetry=v2.14.1\\n");''', 1)
    ctext = ctext.replace('Spanish Dub Study v2.14.0 diagnostics', 'Spanish Dub Study v2.14.1 diagnostics')
    controller.write_text(ctext, encoding="utf-8")

    print("v2.14.1 OpenRouter runtime recovery integration complete")


if __name__ == "__main__":
    main()
