#!/usr/bin/env python3
"""Apply v2.14 against the fully patched v2.13 generated-source shapes.

v2.14 keeps Morphe's normal provider setting authoritative again. OpenRouter therefore uses the
native Morphe streaming implementation when the user selects it; an ordinary OpenRouter failure
latches Google for the remainder of that translation session without changing the saved setting.
"""
from pathlib import Path
import importlib.util
import sys

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "v214_base", HERE / "patch_v214_tts_failover_marker_confidence.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)
ORIG_REP = MOD.rep


def replace_exact(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected final generated-source anchor once, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def compat_rep(path: Path, old: str, new: str, label: str):
    if label == "warm native TTS for persisted active sessions":
        actual_old = '''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) {
            SpanishStudyDiagnostics.record("VIDEO", "load skipped: VoT/session disabled");
            return;
        }
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) {
            SpanishStudyDiagnostics.record("VIDEO", "load deferred: INLINE_MINIMAL");
            return;
        }
        TtsPrefetcher.updateVideo(videoId, segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "requesting transcript at hint=" + videoPositionHint);
        loadTranscript(videoId);'''
        actual_new = '''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) {
            SpanishStudyDiagnostics.record("VIDEO", "load skipped: VoT/session disabled");
            return;
        }
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) {
            SpanishStudyDiagnostics.record("VIDEO", "load deferred: INLINE_MINIMAL");
            return;
        }
        ensureTts(); // warm the local/native reliability floor in parallel with transcript work
        TtsPrefetcher.updateVideo(videoId, segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "requesting transcript at hint=" + videoPositionHint);
        loadTranscript(videoId);'''
        return replace_exact(path, actual_old, actual_new, label)

    if label == "clear failure counters on explicit reset":
        actual_old = '''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();
            currentVideoTimeMs = 0;
            lock.notifyAll();'''
        actual_new = '''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();
            failedAttemptsByIndex.clear();
            currentVideoTimeMs = 0;
            lock.notifyAll();'''
        return replace_exact(path, actual_old, actual_new, label)

    if label == "cap first Google batch near playhead":
        actual_old = '''                if ((isOpenRouter || isGemini) && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;'''
        actual_new = '''                // First audible slice is deliberately small for Google as well as OpenRouter.
                if (firstBatchAfterReposition && !isMyMemory) {
                    capFirstBatch(batches, batchDone, index,
                            isOpenRouter ? OPENROUTER_FIRST_BATCH_CHARS : GOOGLE_FIRST_BATCH_CHARS);
                }
                firstBatchAfterReposition = false;'''
        return replace_exact(path, actual_old, actual_new, label)

    return ORIG_REP(path, old, new, label)


def restore_native_provider(root: Path):
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = votpkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"

    replace_exact(
        translator,
        '''import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        '''import app.spanishstudy.vot.SpanishStudyDiagnostics;
import app.spanishstudy.vot.TranslationProviderPolicy;''',
        "import tested provider policy",
    )

    replace_exact(
        translator,
        '''        // v2.10 stable baseline: only Google translates Spanish Dub Study transcripts.
        String service = TRANSLATION_SERVICE_GOOGLE;
        final boolean isMyMemory = false;
        final boolean isOpenRouter = false;''',
        '''        // v2.14: the normal Morphe translation-provider setting is authoritative again.
        // Select OpenRouter in the standard VoT provider UI to use Morphe's native streaming path.
        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);''',
        "restore native Morphe provider selection",
    )

    replace_exact(
        translator,
        '''    private static volatile boolean reportNextTranslationError;''',
        '''    private static volatile boolean reportNextTranslationError;
    // Once OpenRouter fails for an ordinary provider/network reason, use Google for the rest of
    // this translate() session rather than repeatedly spending latency on the same bad provider.
    private static volatile boolean openRouterFallbackToGoogle;''',
        "add session-latched OpenRouter fallback",
    )

    replace_exact(
        translator,
        '''        abortTranslation = false;
        reprioritize = false;''',
        '''        abortTranslation = false;
        reprioritize = false;
        openRouterFallbackToGoogle = false;''',
        "reset OpenRouter fallback per translation session",
    )

    replace_exact(
        translator,
        '''        if (service.equals(TRANSLATION_SERVICE_OPENROUTER)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        return translateBatchGoogle(videoId, segments, targetLang);''',
        '''        if (TranslationProviderPolicy.shouldUseOpenRouter(service, openRouterFallbackToGoogle)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        // A failed OpenRouter session deliberately stays on Google until translate() completes.
        return translateBatchGoogle(videoId, segments, targetLang);''',
        "route failed OpenRouter session through Google",
    )

    replace_exact(
        translator,
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
        "fail OpenRouter batches forward to Google",
    )

    replace_exact(
        controller,
        '''        report.append("translationMode=google-only-stable\\n");''',
        '''        report.append("translationMode=morphe-native-provider\\n");
        report.append("translationFallback=google-on-openrouter-failure\\n");
        report.append("providerAuthority=normal-morphe-setting\\n");''',
        "diagnose native provider authority and fallback",
    )


MOD.rep = compat_rep

if __name__ == "__main__":
    MOD.main()
    restore_native_provider(Path(sys.argv[1]).resolve())
